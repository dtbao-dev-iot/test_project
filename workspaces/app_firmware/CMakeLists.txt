cmake_minimum_required(VERSION 3.5)
set(SDKCONFIG "${CMAKE_BINARY_DIR}/sdkconfig")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# Version
set(PROJECT_VERSION_MAJOR "26")
set(PROJECT_VERSION_MINOR "06")
set(PROJECT_VERSION_PATCH "00")
set(PROJECT_VERSION_SUFFIX "")
string(TIMESTAMP BUILD_TIME "%d%m%Y")
set(PROJECT_VER "v${PROJECT_VERSION_MAJOR}.${PROJECT_VERSION_MINOR}.${PROJECT_VERSION_PATCH}")
set(PROJECT_AUTHOR "dtbao-IoT")

add_definitions(-DCONFIG_BOOTLOADER_ENABLE=0)

add_definitions(-DPROJECT_TOOLNAME=\"${PROJECT_TOOLNAME}\"
                -DPROJECT_PRODUCT_ID=\"${PROJECT_PRODUCT_ID}\"
                -DFIRMWARE_BUILDNO=\"${FIRMWARE_BUILDNO}\"
                -DBUILD_TIME=\"${BUILD_TIME}\"
                -DPROJECT_VER=\"${PROJECT_VER}\"
                -DPROJECT_AUTHOR=\"${PROJECT_AUTHOR}\"
                )

# Binary name: fw_<product_id>_<toolname>_<DDMMYYYY>_<version>[_<buildno>]
if(PRE_TEST_FIRMWARE AND FIRMWARE_BUILDNO)
    set(PROJECT_BIN "fw_${PROJECT_PRODUCT_ID}_${PROJECT_TOOLNAME}_${BUILD_TIME}_${PROJECT_VER}_${FIRMWARE_BUILDNO}")
    add_definitions(-DPRE_TEST_FIRMWARE=1)
else()
    set(PROJECT_BIN "fw_${PROJECT_PRODUCT_ID}_${PROJECT_TOOLNAME}_${BUILD_TIME}_${PROJECT_VER}")
    add_definitions(-DPRE_TEST_FIRMWARE=0)
endif()

message(STATUS "Building Firmware")
message(STATUS "Project Toolname: ${PROJECT_TOOLNAME}")
message(STATUS "Project Version: ${PROJECT_VER}")
message(STATUS "Project Binary Name: ${PROJECT_BIN}")

# Extra component dirs (uncomment and adjust as needed)
# list(APPEND EXTRA_COMPONENT_DIRS
#     "${CMAKE_CURRENT_SOURCE_DIR}/../../<path_to_extra_component>"
# )

project(${PROJECT_BIN})

idf_build_set_property(COMPILE_OPTIONS "-fdiagnostics-color=always" APPEND)