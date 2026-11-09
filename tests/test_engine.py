import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from contextpilot.engine import pack, scan, rank, terms
from contextpilot.safety import redact, safe_file
from contextpilot.logs import digest_log
from contextpilot.memory import checkpoint, recall, snapshot, changes
from contextpilot.report import html_report
from contextpilot.benchmark import run_benchmark

class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def put(self,path,text):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8');return p

class Retrieval(Workspace):
    def test_target_is_ranked_over_unrelated_sources(self):
        self.put('auth/session.py','def validate_session_expiry():\n    return False\n')
        self.put('catalog.py','name = "shirt"\n'*100)
        result=rank(scan(self.root),'validate session expiry')
        self.assertEqual(result[0]['path'],'auth/session.py')

    def test_pack_has_real_source_line_numbers_and_budget(self):
        self.put('upload.py','\n'.join(['# filler']*50+['def resume_upload_offset():','    return 4096']+['# filler']*50))
        output,report=pack(self.root,'resume upload offset',1000,2)
        self.assertIn('51 | def resume_upload_offset()',output)
        self.assertLessEqual(len(output),1000)
        self.assertEqual(report['outputChars'],len(output))
        self.assertIn('Partial context',output)

    def test_same_size_same_mtime_edit_is_not_stale(self):
        p=self.put('code.py','word = "old"');first=scan(self.root);stamp=p.stat()
        p.write_text('word = "new"',encoding='utf-8');os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        second=scan(self.root)
        self.assertNotEqual(first['files']['code.py']['sha'],second['files']['code.py']['sha'])
        self.assertIn('new',second['files']['code.py']['text'])

    def test_deleted_files_disappear(self):
        p=self.put('obsolete.py','obsolete_symbol=1');scan(self.root);p.unlink()
        self.assertNotIn('obsolete.py',scan(self.root)['files'])

    def test_tampered_cache_text_is_never_served(self):
        self.put('real.py','safe_symbol=1');scan(self.root)
        cache=self.root/'.contextpilot/index.json';cache.write_text('{"files":{"real.py":{"sha":"fake","text":"malicious"}}}')
        output,_=pack(self.root,'safe symbol')
        self.assertIn('safe_symbol',output);self.assertNotIn('malicious',output)

    def test_invalid_cache_recovers(self):
        self.put('real.py','hello=1');scan(self.root)
        for value in ('not json','[]','{"files":[]}'):
            (self.root/'.contextpilot/index.json').write_text(value)
            self.assertEqual(len(scan(self.root)['files']),1)

    def test_no_match_does_not_invent_evidence(self):
        self.put('cats.py','animal="cat"')
        output,report=pack(self.root,'uniquemissingzebra')
        self.assertEqual(report['selected'],[]);self.assertNotIn('animal',output)

    def test_unicode_and_identifier_splitting(self):
        self.assertIn('reservation',terms('InventoryReservation'))
        self.assertIn('stok',terms('STOK çözümü'))

    def test_large_and_binary_sources_are_skipped(self):
        self.put('large.py','x'*512001);(self.root/'binary.py').write_bytes(b'abc\0bad')
        self.assertEqual(scan(self.root)['files'],{})

    def test_negative_reduction_is_not_clamped(self):
        self.put('one.py','x=1')
        _,r=pack(self.root,'one')
        self.assertLess(r['reductionVsSelectedFilesPct'],0)

    def test_invalid_budgets_rejected(self):
        for budget in (1,999,200001):
            with self.assertRaises(ValueError):pack(self.root,'task',budget)

    def test_declaration_survives_dense_matching_literals(self):
        self.put('redact.py','SECRETS = "PRIVATE KEY redact"\n'*4+'\ndef redact(value):\n    return value\n'+'# redact private key\n'*30)
        output,_=pack(self.root,'redact PRIVATE KEY',1000,1)
        self.assertIn('def redact(',output)

    def test_adversarial_long_lines_remain_budgeted(self):
        for i in range(6):self.put('part%d.py'%i,'query_'+('λ'*900)+'\n'*3+'def query_function():\n    pass\n')
        for budget in (1000,1500,4500,12000):
            output,report=pack(self.root,'query function',budget,6)
            self.assertLessEqual(len(output),budget)
            self.assertEqual(len(output),report['outputChars'])

class Safety(Workspace):
    def test_default_exclusions_and_custom_ignore(self):
        for p in ('.env','.env.local','credentials.json','private.key','node_modules/lib.js','dist/site.js','package-lock.json','local.py'):
            self.put(p,'sensitive_marker=1')
        self.put('.contextpilotignore','local.py\n');self.put('app.py','normal=1')
        self.assertEqual(set(scan(self.root)['files']),{'app.py'})

    def test_redaction_applies_to_cache_and_output(self):
        value='sk-'+('a'*30);self.put('app.py','api_key = "'+value+'"\nrun_example()')
        output,_=pack(self.root,'run example')
        self.assertNotIn(value,output)
        self.assertNotIn(value,(self.root/'.contextpilot/index.json').read_text())
        self.assertIn('[REDACTED]',output)

    def test_private_key_redaction_preserves_line_numbers(self):
        text='-----BEGIN PRIVATE KEY-----\nAAAAAA\n-----END PRIVATE KEY-----\nimportant()'
        self.assertEqual(redact(text).splitlines().index('important()'),3)
        self.assertNotIn('AAAAAA',redact(text))

    def test_source_symlink_is_not_followed(self):
        target=self.put('outside.txt','hidden')
        try:(self.root/'linked.py').symlink_to(target)
        except OSError:self.skipTest('Symlinks unavailable for this Windows account')
        self.assertNotIn('linked.py',scan(self.root)['files'])

    def test_cache_symlink_is_rejected(self):
        target=self.root/'elsewhere';target.mkdir()
        try:(self.root/'.contextpilot').symlink_to(target,target_is_directory=True)
        except OSError:self.skipTest('Symlinks unavailable for this Windows account')
        with self.assertRaises(ValueError):scan(self.root)

    def test_path_escape_is_rejected(self):
        self.assertIsNone(safe_file(self.root,'../outside.py'))
        self.assertIsNone(safe_file(self.root,str(self.root/'absolute.py')))

    def test_gitignore_is_respected(self):
        subprocess.run(['git','init',str(self.root)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.put('.gitignore','ignored.py\n');self.put('ignored.py','hidden=1');self.put('visible.py','shown=1')
        result=scan(self.root)
        self.assertEqual(result['discovery'],'git');self.assertNotIn('ignored.py',result['files'])

    def test_report_escapes_scripts(self):
        result=html_report({'query':'<script>alert(1)</script>','selected':[]})
        self.assertNotIn('<script>',result);self.assertIn('&lt;script&gt;',result)
        self.assertIn("default-src 'none'",result)

class LogsAndMemory(Workspace):
    def test_error_at_end_survives_noise(self):
        text='INFO healthy\n'*3000+'ERROR upload failed\nfile.py:100\nAssertionError: bytes changed\n'
        output,report=digest_log(text,1200)
        self.assertIn('ERROR upload failed',output);self.assertIn('file.py:100',output)
        self.assertIn('AssertionError',output);self.assertLessEqual(len(output),1200)
        self.assertGreater(report['reductionPct'],90)

    def test_distinct_errors_survive_deduplication(self):
        output,_=digest_log('ERROR first\n'*100+'ERROR second\n'*100,1200)
        self.assertIn('ERROR first',output);self.assertIn('ERROR second',output)
        self.assertIn('repeated',output)

    def test_ansi_and_credentials_are_removed(self):
        output,_=digest_log('\x1b[31mERROR api_key=abcdef123456\x1b[0m')
        self.assertNotIn('\x1b',output);self.assertNotIn('abcdef123456',output)

    def test_log_without_errors_keeps_tail(self):
        output,_=digest_log('step\n'*20+'Done 42 tests passed')
        self.assertIn('Done 42 tests passed',output)

    def test_checkpoint_is_local_redacted_and_bounded(self):
        checkpoint(self.root,'Upload','api_key=abcdef123456','Check retries')
        self.assertIn('Check retries',recall(self.root));self.assertNotIn('abcdef123456',recall(self.root))
        with self.assertRaises(ValueError):checkpoint(self.root,'x'*4001,'','next')
        self.assertFalse((self.root/'AGENTS.md').exists())

    def test_changes_detect_added_modified_deleted(self):
        a=self.put('a.py','one=1');b=self.put('b.py','two=2');snapshot(self.root)
        a.write_text('one=9');b.unlink();self.put('c.py','three=3')
        r=changes(self.root)
        self.assertEqual(r['modified'],['a.py']);self.assertEqual(r['deleted'],['b.py']);self.assertEqual(r['added'],['c.py'])

    def test_synthetic_benchmark_retains_labelled_evidence(self):
        result=run_benchmark(self.root/'results')
        self.assertEqual(result['evidenceRecall'],1)
        self.assertTrue(result['log']['requiredEvidencePreserved'])
        for case in result['cases']:self.assertLessEqual(case['outputChars'],4500)

if __name__=='__main__': unittest.main()
