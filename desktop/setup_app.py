"""Build AUSTR.AI as a macOS .app bundle."""

from setuptools import setup

APP = ["austrai_app.py"]

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "AUSTR.AI",
        "CFBundleDisplayName": "AUSTR.AI",
        "CFBundleIdentifier": "at.austr.ai",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
    "packages": ["austrai_proxy", "webview", "spacy", "presidio_analyzer", "cryptography"],
    "includes": ["webview", "austrai_proxy.core"],
}

setup(
    name="AUSTR.AI",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
