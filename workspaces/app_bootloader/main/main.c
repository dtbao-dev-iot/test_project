/**
 * @file    main.c
 * @author  dtbao-IoT
 * @brief   Bootloader application entry point
 * @date    2026-04-19
 * @copyright Copyright (c) 2026 dtbao-IoT. All rights reserved.
 */

#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "esp_log.h"

#define TAG "main"

void app_main(void)
{
    ESP_LOGI(TAG, "Bootloader started — version: %s", PROJECT_VER);

    while (1)
    {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}