# ──────────────────────────────────────────────────────────────
# config_workspace — Central source registration for Bootloader
#
# Register all source files, include dirs, and component
# dependencies here so main/CMakeLists.txt stays minimal.
# Bootloader typically has fewer sources than Firmware.
# ──────────────────────────────────────────────────────────────

# list(APPEND SOURCE_C
#     # applications/ (bootloader-specific only)
#     "../../../../applications/<bootloader_module>/<source>.c"
#
#     # middlewares/ (minimal subset for bootloader)
#     "../../../../middlewares/<module>/<source>.c"
#
#     # drivers/ (minimal subset for bootloader)
#     "../../../../drivers/<module>/<source>.c"
#     )

# list(APPEND SOURCE_INCLUDE_DIRS
#     "../../../../"
#     "../../../../applications"
#     "../../../../middlewares"
#     "../../../../drivers"
#     "../../../../configs_tool"
#     )

# list(APPEND SOURCE_REQUIRES
#     "driver"
#     "nvs_flash"
#     "bootloader_support"
#     "app_update"
#     "fatfs"
#     )

# idf_component_register(SRCS ${SOURCE_C}
#                         INCLUDE_DIRS ${SOURCE_INCLUDE_DIRS}
#                         REQUIRES ${SOURCE_REQUIRES}
#                         )