"""Works from a checkout or from the self-contained installed skill."""
import sys
from pathlib import Path
here = Path(__file__).resolve().parent
if not (here / 'contextpilot').is_dir():
    sys.path.insert(0, str(here.parents[2] / 'src'))
from contextpilot.cli import main
raise SystemExit(main())
