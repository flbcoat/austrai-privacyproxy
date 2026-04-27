import os, warnings, logging
# HuggingFace Hub spam suppression. The "unauthenticated requests" notice
# and telemetry probes are printed directly to stderr from hf_hub internals
# before any user-level warnings filter can catch them. The env vars below
# cover the three channels (progress bars, telemetry pings, anonymous-user
# notice). HF_HUB_DISABLE_SYMLINKS_WARNING quiets the Windows cache warning.
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*unauthenticated.*")
warnings.filterwarnings("ignore", message=".*HF_TOKEN.*")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)

# The "Warning: You are sending unauthenticated requests..." message is
# printed via `print(..., file=sys.stderr)` from huggingface_hub, bypassing
# both the warnings filter and the logger. We intercept stderr for the one
# known line only; everything else passes through unmodified so real errors
# still appear.
def _install_hf_stderr_filter() -> None:
    import sys as _sys
    _real_stderr = _sys.stderr
    _SUPPRESS_MARKERS = (
        "unauthenticated requests to the HF Hub",
        "Please set a HF_TOKEN",
    )

    class _FilteringStderr:
        def write(self, data):
            if any(m in data for m in _SUPPRESS_MARKERS):
                return len(data)
            return _real_stderr.write(data)
        def flush(self):
            return _real_stderr.flush()
        def __getattr__(self, name):
            return getattr(_real_stderr, name)

    _sys.stderr = _FilteringStderr()

_install_hf_stderr_filter()

"""AUSTR.AI Privacy Proxy — transparent anonymization layer for LLM APIs."""

__version__ = "3.2.0"
