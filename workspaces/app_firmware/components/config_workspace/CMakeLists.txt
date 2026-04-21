# ──────────────────────────────────────────────────────────────
# config_workspace — Central source registration for Firmware
#
# Register all source files, include dirs, and component
# dependencies here so main/CMakeLists.txt stays minimal.
# ──────────────────────────────────────────────────────────────

# list(APPEND SOURCE_C
#     # applications/
#     "../../../../applications/<module>/<source>.c"
#
#     # middlewares/
#     "../../../../middlewares/<module>/<source>.c"
#
#     # drivers/
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
#     "esp_timer"
#     "esp_wifi"
#     "bt"
#     "fatfs"
#     )

# idf_component_register(SRCS ${SOURCE_C}
#                         INCLUDE_DIRS ${SOURCE_INCLUDE_DIRS}
#                         REQUIRES ${SOURCE_REQUIRES}
#                         )