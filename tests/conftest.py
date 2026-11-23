import os

# Must be set before "app.main" is imported, so the module-level app uses fakes
# and never tries to reach Azure during tests.
os.environ["USE_FAKES"] = "true"
