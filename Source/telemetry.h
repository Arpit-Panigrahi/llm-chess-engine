/*
 * telemetry.h — CSV telemetry logging interface
 * Author: Arpit Panigrahi (2026)
 */
#ifndef TELEMETRY_H
#define TELEMETRY_H

// Appends a single row of telemetry to llm_research_log.csv safely
void LogLLMAction(const char *fen, float temperature, long latency_ms, 
                  const char *raw_response, const char *uci_move, 
                  int is_legal, int fallback_used);

#endif