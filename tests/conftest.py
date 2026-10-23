"""Keep the test suite offline, including LiteLLM's import-time price lookup."""

import os

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
