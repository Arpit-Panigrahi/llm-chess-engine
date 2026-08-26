#ifndef LLM_PARSER_H
#define LLM_PARSER_H

#include "defs.h"

// Scans a free-form text block and extracts the first valid UCI move token.
void ExtractUCI(const char *raw_response, char *uci_move);

// Enhanced version that also matches SAN (e.g. Nf3, O-O, exd5) against legal moves if coordinate parsing fails.
void ExtractUCIEnhanced(const char *raw_response, char *uci_move, S_BOARD *pos);

#endif
