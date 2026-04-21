idf_component_register(SRCS "main.c"
                    INCLUDE_DIRS "."
                    )

# Add global config headers as forced includes (adjust paths to your project)
# target_compile_options(${COMPONENT_LIB} PRIVATE
#     $<$<COMPILE_LANGUAGE:C,CXX>:-include${CMAKE_CURRENT_SOURCE_DIR}/../../../configs_tool/board_config.h>
#     $<$<COMPILE_LANGUAGE:C,CXX>:-include${CMAKE_CURRENT_SOURCE_DIR}/../../../configs_tool/system_config.h>
# )