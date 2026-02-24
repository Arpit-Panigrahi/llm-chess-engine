/*
 * llm_parser.c — UCI move extraction from LLM responses
 * Author: Arpit Panigrahi (2026)
 * Part of the LLM integration layer added to VICE.
 * Original VICE engine by Richard Allbert (Bluefever Software).
 */

// Extracts the first syntactically valid UCI move (e.g. e2e4,
// e7e8q) from an arbitrary natural-language LLM response.

#include "llm_parser.h"
#include <string.h>
#include <ctype.h>
#include <stdio.h>

// Helper function to check if a single word is a valid UCI move
static int IsValidUCIMove(const char *token) {
    size_t len = strlen(token);
    
    // A standard move is 4 chars (e2e4). A promotion is 5 chars (e7e8q).
    if (len != 4 && len != 5) {
        return 0;
    }

    // Check strict UCI coordinate boundaries: [a-h][1-8][a-h][1-8]
    if (token[0] < 'a' || token[0] > 'h') return 0; // File from
    if (token[1] < '1' || token[1] > '8') return 0; // Rank from
    if (token[2] < 'a' || token[2] > 'h') return 0; // File to
    if (token[3] < '1' || token[3] > '8') return 0; // Rank to

    // If it's a promotion (length 5), ensure the last char is a valid piece
    if (len == 5) {
        char p = tolower(token[4]);
        if (p != 'q' && p != 'r' && p != 'b' && p != 'n') {
            return 0;
        }
    }

    return 1; // It is a mathematically perfect UCI string!
}

void ExtractUCI(const char *raw_response, char *uci_move) {
    // 1. Default the output to empty, just in case we find nothing
    uci_move[0] = '\0'; 
    if (raw_response == NULL) return;

    // 2. Create a local copy of the response string. 
    // strtok modifies the string it works on, so we NEVER pass the original.
    char temp_buffer[2048];
    strncpy(temp_buffer, raw_response, sizeof(temp_buffer) - 1);
    temp_buffer[sizeof(temp_buffer) - 1] = '\0';

    // 3. Define our delimiters (what separates the words)
    // We strip out spaces, newlines, and common punctuation Llama might use.
    const char *delimiters = " \n\r\t.,:;\"'()[]{}*";

    // 4. Tokenize and scan
    char *token = strtok(temp_buffer, delimiters);
    
    while (token != NULL) {
        // Force the token to lowercase just to be safe (e.g., if LLM outputs "E2E4")
        for (int i = 0; token[i]; i++) {
            token[i] = tolower(token[i]);
        }

        // 5. Check if this specific word is our chess move
        if (IsValidUCIMove(token)) {
            // We found it! Copy it to the output variable and exit the function immediately.
            strcpy(uci_move, token);
            return; 
        }

        // Move to the next word
        token = strtok(NULL, delimiters);
    }
}