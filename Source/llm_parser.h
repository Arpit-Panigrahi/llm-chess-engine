#ifndef LLM_PARSER_H
#define LLM_PARSER_H

// LLM parser: scans a free-form text block (e.g. an LLM reply)
// and extracts the first valid 4/5-character UCI move token.
void ExtractUCI(const char *raw_response, char *uci_move);

#endif
