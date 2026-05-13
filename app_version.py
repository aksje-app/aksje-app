APP_VERSION = "v18.5.71"
APP_VERSION_NAME = "Security Metadata Hydration Fix"
APP_BUILD_LABEL = f"{APP_VERSION} {APP_VERSION_NAME}"
APP_BUILD_ID = "v18571-security-metadata-hydration"

def get_app_version() -> str:
    return APP_VERSION

def get_app_build_label() -> str:
    return APP_BUILD_LABEL

def get_app_build_id() -> str:
    return APP_BUILD_ID
