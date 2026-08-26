/*
 * http_client.h — Ollama HTTP client interface
 * Author: Arpit Panigrahi (2026)
 */
#ifndef HTTP_CLIENT_H
#define HTTP_CLIENT_H

#include <stddef.h> // For size_t

// Sends the FEN + optional legal moves to the LLM and populates raw_response. Returns 1 on success, 0 on failure.
int GetMoveFromOllama(const char *fen, float temperature, const char *legal_moves, 
                      const char *model, const char *url, int timeout_s, int constrained,
                      char *raw_response, size_t response_size);

#endif