/*
 * llm_parser.c — UCI move extraction from LLM responses
 * Author: Arpit Panigrahi (2026)
 * Part of the LLM integration layer added to VICE.
 * Original VICE engine by Richard Allbert (Bluefever Software).
 */

#include "llm_parser.h"
#include <string.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>

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
        char p = tolower((unsigned char)token[4]);
        if (p != 'q' && p != 'r' && p != 'b' && p != 'n') {
            return 0;
        }
    }

    return 1;
}

// Clean and normalize a token candidate (strip prefixes, dashes, capture marks, equals)
static void CleanCandidate(const char *in, char *out, size_t out_size) {
    size_t j = 0;
    size_t in_len = strlen(in);
    size_t start = 0;

    // Skip leading piece letters if followed by coordinate: e.g. "Nb8c6" -> "b8c6", "Pe2e4" -> "e2e4"
    if (in_len >= 5 && (in[0]=='N'||in[0]=='n'||in[0]=='B'||in[0]=='b'||in[0]=='R'||in[0]=='r'||
                       in[0]=='Q'||in[0]=='q'||in[0]=='K'||in[0]=='k'||in[0]=='P'||in[0]=='p')) {
        if (in[1] >= 'a' && in[1] <= 'h' && in[2] >= '1' && in[2] <= '8') {
            start = 1;
        }
    }

    for (size_t i = start; i < in_len && j + 1 < out_size; i++) {
        char c = (char)tolower((unsigned char)in[i]);
        if ((c >= 'a' && c <= 'h') || (c >= '1' && c <= '8') || c == 'q' || c == 'r' || c == 'b' || c == 'n') {
            out[j++] = c;
        }
    }
    out[j] = '\0';
}

void ExtractUCI(const char *raw_response, char *uci_move) {
    uci_move[0] = '\0'; 
    if (raw_response == NULL) return;

    char temp_buffer[4096];
    strncpy(temp_buffer, raw_response, sizeof(temp_buffer) - 1);
    temp_buffer[sizeof(temp_buffer) - 1] = '\0';

    const char *delimiters = " \n\r\t.,:;\"'()[]{}*`";
    char *saveptr = NULL;
    char *token = strtok_r(temp_buffer, delimiters, &saveptr);
    
    while (token != NULL) {
        // Direct test
        char lower_token[64] = {0};
        for (int i = 0; token[i] && i < 63; i++) {
            lower_token[i] = (char)tolower((unsigned char)token[i]);
        }

        if (IsValidUCIMove(lower_token)) {
            strncpy(uci_move, lower_token, 9);
            uci_move[9] = '\0';
            return; 
        }

        // Cleaned candidate test (handles Nb8-c6, e2-e4, e7-e8=q)
        char cleaned[64] = {0};
        CleanCandidate(token, cleaned, sizeof(cleaned));
        if (IsValidUCIMove(cleaned)) {
            strncpy(uci_move, cleaned, 9);
            uci_move[9] = '\0';
            return;
        }

        token = strtok_r(NULL, delimiters, &saveptr);
    }
}

// Case-insensitive substring search
static int ContainsWord(const char *haystack, const char *needle) {
    if (!haystack || !needle || !*needle) return 0;
    size_t h_len = strlen(haystack);
    size_t n_len = strlen(needle);
    if (n_len > h_len) return 0;

    for (size_t i = 0; i <= h_len - n_len; i++) {
        size_t j;
        for (j = 0; j < n_len; j++) {
            if (tolower((unsigned char)haystack[i + j]) != tolower((unsigned char)needle[j])) {
                break;
            }
        }
        if (j == n_len) {
            // Check boundary
            int left_ok = (i == 0 || !isalnum((unsigned char)haystack[i - 1]));
            int right_ok = (i + n_len == h_len || !isalnum((unsigned char)haystack[i + n_len]));
            if (left_ok && right_ok) return 1;
        }
    }
    return 0;
}

void ExtractUCIEnhanced(const char *raw_response, char *uci_move, S_BOARD *pos) {
    uci_move[0] = '\0';
    if (!raw_response) return;

    // 1. Try standard coordinate UCI extraction first
    ExtractUCI(raw_response, uci_move);
    if (pos && strlen(uci_move) > 0) {
        int parsed = ParseMove(uci_move, pos);
        if (parsed != NOMOVE) {
            return; // Valid legal coordinate move
        }
    } else if (strlen(uci_move) > 0) {
        return;
    }

    if (!pos) return;

    // 2. Fallback: match SAN or algebraic tokens against legal moves
    S_MOVELIST list[1];
    GenerateAllMoves(pos, list);

    // Castling checks
    if (ContainsWord(raw_response, "o-o-o") || ContainsWord(raw_response, "0-0-0")) {
        const char *castle_uci = (pos->side == WHITE) ? "e1c1" : "e8c8";
        if (ParseMove((char*)castle_uci, pos) != NOMOVE) {
            strcpy(uci_move, castle_uci);
            return;
        }
    }
    if (ContainsWord(raw_response, "o-o") || ContainsWord(raw_response, "0-0")) {
        const char *castle_uci = (pos->side == WHITE) ? "e1g1" : "e8g8";
        if (ParseMove((char*)castle_uci, pos) != NOMOVE) {
            strcpy(uci_move, castle_uci);
            return;
        }
    }

    // Check each legal move's SAN tokens
    for (int i = 0; i < list->count; ++i) {
        int move = list->moves[i].move;
        if (!MakeMove(pos, move)) continue;
        TakeMove(pos);

        char *mv_uci = PrMove(move);

        // Check coordinate in text
        if (ContainsWord(raw_response, mv_uci)) {
            strcpy(uci_move, mv_uci);
            return;
        }

        // Build piece SAN notation: e.g. "Nf3", "Bxf7", "exd5", "e4", "e8=Q"
        int pce = pos->pieces[FROMSQ(move)];
        int to_sq = TOSQ(move);
        char to_str[3];
        to_str[0] = 'a' + FilesBrd[to_sq];
        to_str[1] = '1' + RanksBrd[to_sq];
        to_str[2] = '\0';

        char san1[16] = {0};
        char san2[16] = {0};

        if (IsKn(pce)) {
            snprintf(san1, sizeof(san1), "N%s", to_str);
            snprintf(san2, sizeof(san2), "Nx%s", to_str);
        } else if (IsBQ(pce) && !IsRQ(pce)) {
            snprintf(san1, sizeof(san1), "B%s", to_str);
            snprintf(san2, sizeof(san2), "Bx%s", to_str);
        } else if (IsRQ(pce) && !IsBQ(pce)) {
            snprintf(san1, sizeof(san1), "R%s", to_str);
            snprintf(san2, sizeof(san2), "Rx%s", to_str);
        } else if (IsRQ(pce) && IsBQ(pce)) {
            snprintf(san1, sizeof(san1), "Q%s", to_str);
            snprintf(san2, sizeof(san2), "Qx%s", to_str);
        } else if (IsKi(pce)) {
            snprintf(san1, sizeof(san1), "K%s", to_str);
            snprintf(san2, sizeof(san2), "Kx%s", to_str);
        } else {
            // Pawn move
            snprintf(san1, sizeof(san1), "%s", to_str);
            char from_file = 'a' + FilesBrd[FROMSQ(move)];
            snprintf(san2, sizeof(san2), "%cx%s", from_file, to_str);
        }

        if (strlen(san1) > 0 && ContainsWord(raw_response, san1)) {
            strcpy(uci_move, mv_uci);
            return;
        }
        if (strlen(san2) > 0 && ContainsWord(raw_response, san2)) {
            strcpy(uci_move, mv_uci);
            return;
        }
    }
}