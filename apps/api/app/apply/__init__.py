"""Auto-apply engine: adapters, blocker detection, caps-aware graph and the worker.

Safety model (every rule has a test in tests/test_apply_*.py):
- the worker only talks to the target host (plus our API); everything else is
  route-blocked, and wellfound/naukri/hiring.cafe/linkedin are refused outright;
- CAPTCHA, login, verification and bot checks are detected and STOPPED, never solved;
- nothing is submitted unless every required field came from an allowed source and
  the uploaded file is the run's approved PDF.
"""
