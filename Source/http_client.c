/*
 * http_client.c — Ollama HTTP client via libcurl
 * Author: Arpit Panigrahi (2026)
 * Part of the LLM integration layer added to VICE.
 * Original VICE engine by Richard Allbert (Bluefever Software).
 */
#include "http_client.h"
#include "cJSON.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <curl/curl.h>

// 1. Structure to hold the raw HTTP response in memory
struct MemoryStruct {
    char *memory;
    size_t size;
};

// 2. The callback function libcurl uses to write incoming data into our memory struct
static size_t WriteMemoryCallback(void *contents, size_t size, size_t nmemb, void *userp) {
    size_t realsize = size * nmemb;
    struct MemoryStruct *mem = (struct MemoryStruct *)userp;

    char *ptr = realloc(mem->memory, mem->size + realsize + 1);
    if(ptr == NULL) {
        printf("Not enough memory (realloc returned NULL)\n");
        return 0;
    }

    mem->memory = ptr;
    memcpy(&(mem->memory[mem->size]), contents, realsize);
    mem->size += realsize;
    mem->memory[mem->size] = 0; // Null-terminate the string

    return realsize;
}

// 3. The main function to talk to Ollama
int GetMoveFromOllama(const char *fen, float temperature, const char *legal_moves, 
                      const char *model, const char *url, int timeout_s, int constrained,
                      char *raw_response, size_t response_size) {
    CURL *curl;
    CURLcode res;
    int success = 0;

    // Initialize our memory struct to empty
    struct MemoryStruct chunk;
    chunk.memory = malloc(1);  
    chunk.size = 0;    

    curl = curl_easy_init();

    if(curl) {
        // --- A. Build the JSON Payload ---
        cJSON *root = cJSON_CreateObject();
        cJSON_AddStringToObject(root, "model", (model && strlen(model) > 0) ? model : "llama3");
        
        // Parse active color from FEN (the char right after the first space)
        const char *side_str = "White";
        const char *space = strchr(fen, ' ');
        if (space && *(space + 1) == 'b') side_str = "Black";

        char prompt[8192];
        if (constrained && legal_moves && strlen(legal_moves) > 0) {
            snprintf(prompt, sizeof(prompt), 
                "You are a chess engine playing as %s. "
                "The current board FEN is: %s. "
                "It is %s's turn to move. "
                "The ONLY legal moves in this position are: %s. "
                "You MUST pick exactly one move from that list. "
                "Respond ONLY with a single 4-character UCI move (e.g., e7e5). "
                "Do not include any other text, explanations, or formatting.",
                side_str, fen, side_str, legal_moves);
        } else {
            snprintf(prompt, sizeof(prompt), 
                "You are a chess engine playing as %s. "
                "The current board FEN is: %s. "
                "It is %s's turn to move. "
                "Respond ONLY with a single UCI move in source-destination format "
                "(e.g., g8f6, e7e5, b8c6, d7d5). "
                "Do not include piece letters, just the two squares. "
                "Do not include any other text, explanations, or formatting.",
                side_str, fen, side_str);
        }
            
        cJSON_AddStringToObject(root, "prompt", prompt);
        cJSON_AddBoolToObject(root, "stream", 0); // We want one single response, no streaming
        
        cJSON *options = cJSON_CreateObject();
        cJSON_AddNumberToObject(options, "temperature", temperature);
        cJSON_AddItemToObject(root, "options", options);

        char *json_payload = cJSON_PrintUnformatted(root);

        // --- B. Configure libcurl ---
        struct curl_slist *headers = NULL;
        headers = curl_slist_append(headers, "Content-Type: application/json");

        const char *target_url = (url && strlen(url) > 0) ? url : "http://localhost:11434/api/generate";
        curl_easy_setopt(curl, CURLOPT_URL, target_url);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_payload);
        
        // Wire up our memory callback
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, WriteMemoryCallback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, (void *)&chunk);
        
        long timeout_val = (timeout_s > 0) ? (long)timeout_s : 30L;
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, timeout_val); 

        // --- C. Execute the Request ---
        res = curl_easy_perform(curl);

        if(res == CURLE_OK) {
            // --- D. Parse the JSON Response ---
            cJSON *response_json = cJSON_Parse(chunk.memory);
            if (response_json != NULL) {
                cJSON *llm_reply = cJSON_GetObjectItemCaseSensitive(response_json, "response");
                if (cJSON_IsString(llm_reply) && (llm_reply->valuestring != NULL)) {
                    // Copy the LLM's text into our output variable safely
                    strncpy(raw_response, llm_reply->valuestring, response_size - 1);
                    raw_response[response_size - 1] = '\0';
                    success = 1;
                }
                cJSON_Delete(response_json);
            }
        } else {
            printf("info string HTTP Error: %s\n", curl_easy_strerror(res));
        }

        // --- E. Cleanup Memory ---
        curl_slist_free_all(headers);
        cJSON_free(json_payload);
        cJSON_Delete(root);
        curl_easy_cleanup(curl);
    }

    free(chunk.memory);

    return success;
}