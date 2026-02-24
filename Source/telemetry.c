#include "telemetry.h"
#include <stdio.h>
#include <time.h>
#include <string.h>
#include <sys/stat.h>

// Helper to remove newlines, commas, and quotes so the CSV format doesn't break
static void SanitizeString(char *str) {
    if (!str) return;
    for (int i = 0; str[i]; i++) {
        if (str[i] == ',' || str[i] == '\n' || str[i] == '\r' || str[i] == '"') {
            str[i] = ' '; // Replace structural characters with a safe space
        }
    }
}

void LogLLMAction(const char *fen, float temperature, long latency_ms, 
                  const char *raw_response, const char *uci_move, 
                  int is_legal, int fallback_used) {
    
    // 1. Ensure the data/ directory exists (no-op if already present)
    mkdir("data", 0755);

    // 2. Open in Append mode ("a"). 
    // This adds to the end of the file, or creates it if it doesn't exist.
    FILE *log_file = fopen("data/llm_research_log.csv", "a");
    if (log_file == NULL) {
        // If we can't open the file (e.g., a permissions error in Fedora), just return.
        // We NEVER want a logging failure to crash the actual chess engine.
        return; 
    }

    // 2. Get a standard UNIX timestamp for chronological sorting
    time_t now = time(NULL);

    // 3. Create local copies of the strings so we can sanitize them safely
    char safe_response[2048] = {0};
    if (raw_response) {
        strncpy(safe_response, raw_response, sizeof(safe_response) - 1);
        SanitizeString(safe_response);
    }

    char safe_move[10] = {0};
    if (uci_move) {
        strncpy(safe_move, uci_move, sizeof(safe_move) - 1);
        SanitizeString(safe_move);
    }

    // 4. Write the row to the CSV. 
    // Columns: Timestamp, FEN, Temperature, Latency(ms), Extracted_Move, Is_Legal, Fallback_Used, Raw_Response
    fprintf(log_file, "%ld,%s,%.2f,%ld,%s,%d,%d,%s\n", 
            (long)now, 
            fen, 
            temperature, 
            latency_ms, 
            safe_move, 
            is_legal, 
            fallback_used, 
            safe_response);

    // 5. Save the file to the disk and free the memory pointer
    fclose(log_file);
}