/*
 * llm_search.c — LLM move search entry point
 * Author: Arpit Panigrahi (2026)
 * Part of the LLM integration layer added to VICE.
 * Original VICE engine by Richard Allbert (Bluefever Software).
 */
#include "defs.h"
#include "http_client.h"
#include "llm_parser.h"
#include "telemetry.h"
#include <stdio.h>
#include <string.h>
#include <sys/time.h>

// Assuming you placed your BoardToFen function here or in a utility file
extern void BoardToFen(const S_BOARD *pos, char *fen);

// Build a JSON array of all legal UCI moves for the current position.
// This is injected into the LLM prompt to constrain its output to only valid moves.
static void BuildLegalMoveString(S_BOARD *pos, char *out, size_t out_size) {
    // 1. Create a buffer large enough to hold all possible legal moves
    strcpy(out, "["); 
    S_MOVELIST list[1];
    size_t current_len = 1; // accounts for "["

    // 2. Generate all pseudo-legal moves for the current position
    GenerateAllMoves(pos, list);

    int moveNum = 0;
    int isFirstMove = 1;

    // 3. Loop through every generated move
    for(moveNum = 0; moveNum < list->count; ++moveNum) {
        
        // 4. Test if the move is strictly legal (doesn't leave the King in check)
        if ( !MakeMove(pos, list->moves[moveNum].move))  {
            continue; // If illegal, skip it!
        }
        
        // 5. The move is legal! Take it back to restore the board state
        TakeMove(pos);
        
        // 6. Check buffer space: worst case per move is ", " + '"' + move(5) + '"' = 10 chars
        //    Plus 2 for closing "]" and null terminator
        const char *move_str = PrMove(list->moves[moveNum].move);
        size_t needed = (isFirstMove ? 0 : 2) + 1 + strlen(move_str) + 1; // separator + quotes + move
        if (current_len + needed + 2 >= out_size) { // +2 for "]\0"
            printf("info string WARNING: Legal move buffer full, truncating\n");
            break;
        }
        
        // 7. Append the move to our JSON array string
        if (!isFirstMove) {
            strcat(out, ", ");
            current_len += 2;
        }
        
        strcat(out, "\"");
        strcat(out, move_str);
        strcat(out, "\"");
        current_len += 1 + strlen(move_str) + 1;
        
        isFirstMove = 0;
    }

    // 8. Close the JSON array
    strcat(out, "]");

    // FOR DEBUGGING: Print it to the console so you can see it working!
    printf("info string Generated Legal Moves Array: %s\n", out);
}

void SearchPosition(S_BOARD *pos, S_SEARCHINFO *info) {
    // 1. If LLM is disabled, use classical alpha-beta minimax directly
    if (!EngineOptions->LLM_Enabled) {
        SearchPosition_Classical(pos, info);
        return;
    }

    char fen[256] = {0};
    char raw_response[4096] = {0};
    char uci_move[16] = {0};
    char legal_moves_str[8192] = {0};
    float temperature = EngineOptions->LLM_Temperature;
    
    int is_legal = 0;
    int fallback_used = 1; // Default to triggering fallback
    long latency_ms = 0;

    // 2. Clear VICE's search structures
    ClearForSearch(pos, info);

    // 3. Generate the FEN string for Ollama
    BoardToFen(pos, fen);

    // 4. Generate the legal move array if constrained decoding is on
    if (EngineOptions->LLM_Constrained) {
        BuildLegalMoveString(pos, legal_moves_str, sizeof(legal_moves_str));
    }

    // Start Timer
    struct timeval start, end;
    gettimeofday(&start, NULL);

    // 5. Request move from Ollama
    printf("info string LLM is thinking (model=%s, temp=%.2f, constr=%d)...\n", 
           EngineOptions->LLM_Model, temperature, EngineOptions->LLM_Constrained);
    
    if (GetMoveFromOllama(fen, temperature, 
                          EngineOptions->LLM_Constrained ? legal_moves_str : NULL,
                          EngineOptions->LLM_Model, 
                          EngineOptions->LLM_Url, 
                          EngineOptions->LLM_Timeout, 
                          EngineOptions->LLM_Constrained,
                          raw_response, sizeof(raw_response))) {
        
        // 6. Extract the UCI / SAN move
        ExtractUCIEnhanced(raw_response, uci_move, pos);
        
        if (strlen(uci_move) > 0) {
            // 7. VALIDATION: Check if move is legal
            int parsed_move = ParseMove(uci_move, pos);
            
            if (parsed_move != NOMOVE && MakeMove(pos, parsed_move)) {
                TakeMove(pos); // Restore board state
                // SUCCESS! The LLM generated a strictly legal move.
                is_legal = 1;
                fallback_used = 0;
                
                // End Timer early
                gettimeofday(&end, NULL);
                latency_ms = ((end.tv_sec - start.tv_sec) * 1000) + ((end.tv_usec - start.tv_usec) / 1000);

                // Output the move adhering to UCI / XBoard protocol
                if (info->GAME_MODE == UCIMODE) {
                    printf("bestmove %s\n", PrMove(parsed_move));
                } else if (info->GAME_MODE == XBOARDMODE) {
                    printf("move %s\n", PrMove(parsed_move));
                    MakeMove(pos, parsed_move);
                } else {
                    printf("\n\n***!! LLM makes move %s !!***\n\n", PrMove(parsed_move));
                    MakeMove(pos, parsed_move);
                    PrintBoard(pos);
                }
            }
        }
    }

    if (fallback_used) {
        // End Timer (if LLM failed or timed out)
        gettimeofday(&end, NULL);
        latency_ms = ((end.tv_sec - start.tv_sec) * 1000) + ((end.tv_usec - start.tv_usec) / 1000);
        
        printf("info string LLM Failed/Illegal. Falling back to Classical Minimax.\n");
        
        // Trigger VICE's original logic
        SearchPosition_Classical(pos, info);
    }

    // 8. Log the exact telemetry for research
    LogLLMAction(fen, temperature, latency_ms, raw_response, uci_move, is_legal, fallback_used);
}
