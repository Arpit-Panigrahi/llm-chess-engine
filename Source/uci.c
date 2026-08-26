// uci.c
// UCI protocol implementation: parses position/go/setoption
// commands, manages time settings and launches SearchPosition,
// printing bestmove and optional search info.

#include "stdio.h"
#include "defs.h"
#include "string.h"

#define INPUTBUFFER (400 * 6)

// go depth 6 wtime 180000 btime 100000 binc 1000 winc 1000 movetime 1000 movestogo 40
void ParseGo(char* line, S_SEARCHINFO *info, S_BOARD *pos) {

	int depth = -1, movestogo = 30,movetime = -1;
	int time = -1, inc = 0;
    char *ptr = NULL;
	info->timeset = FALSE;

	if ((ptr = strstr(line,"infinite"))) {
		;
	}

	if ((ptr = strstr(line,"binc")) && pos->side == BLACK) {
		inc = atoi(ptr + 5);
	}

	if ((ptr = strstr(line,"winc")) && pos->side == WHITE) {
		inc = atoi(ptr + 5);
	}

	if ((ptr = strstr(line,"wtime")) && pos->side == WHITE) {
		time = atoi(ptr + 6);
	}

	if ((ptr = strstr(line,"btime")) && pos->side == BLACK) {
		time = atoi(ptr + 6);
	}

	if ((ptr = strstr(line,"movestogo"))) {
		movestogo = atoi(ptr + 10);
	}

	if ((ptr = strstr(line,"movetime"))) {
		movetime = atoi(ptr + 9);
	}

	if ((ptr = strstr(line,"depth"))) {
		depth = atoi(ptr + 6);
	}

	if(movetime != -1) {
		time = movetime;
		movestogo = 1;
	}

	info->starttime = GetTimeMs();
	info->depth = depth;

	if(time != -1) {
		info->timeset = TRUE;
		time /= movestogo;
		time -= 50;
		info->stoptime = info->starttime + time + inc;
	}

	if(depth == -1) {
		info->depth = MAXDEPTH;
	}

	printf("time:%d start:%d stop:%d depth:%d timeset:%d\n",
		time,info->starttime,info->stoptime,info->depth,info->timeset);
	SearchPosition(pos, info);
}

// position fen fenstr
// position startpos
// ... moves e2e4 e7e5 b7b8q
void ParsePosition(char* lineIn, S_BOARD *pos) {

	lineIn += 9;
    char *ptrChar = lineIn;

    if(strncmp(lineIn, "startpos", 8) == 0){
        ParseFen(START_FEN, pos);
    } else {
        ptrChar = strstr(lineIn, "fen");
        if(ptrChar == NULL) {
            ParseFen(START_FEN, pos);
        } else {
            ptrChar+=4;
            ParseFen(ptrChar, pos);
        }
    }

	ptrChar = strstr(lineIn, "moves");
	int move;

	if(ptrChar != NULL) {
        ptrChar += 6;
        while(*ptrChar) {
              move = ParseMove(ptrChar,pos);
			  if(move == NOMOVE) break;
			  MakeMove(pos, move);
              pos->ply=0;
              while(*ptrChar && *ptrChar!= ' ') ptrChar++;
              ptrChar++;
        }
    }
	PrintBoard(pos);
}

static void PrintUciInfo() {
    printf("id name %s\n",NAME);
    printf("id author Bluefever (LLM additions by Arpit Panigrahi)\n");
	printf("option name Hash type spin default 64 min 4 max %d\n",MAX_HASH);
	printf("option name Book type check default %s\n", EngineOptions->UseBook ? "true" : "false");
	printf("option name LLM_Enabled type check default %s\n", EngineOptions->LLM_Enabled ? "true" : "false");
	printf("option name LLM_Model type string default %s\n", EngineOptions->LLM_Model);
	printf("option name LLM_Url type string default %s\n", EngineOptions->LLM_Url);
	printf("option name LLM_Temperature type string default %.2f\n", EngineOptions->LLM_Temperature);
	printf("option name LLM_Constrained type check default %s\n", EngineOptions->LLM_Constrained ? "true" : "false");
	printf("option name LLM_Timeout type spin default %d min 1 max 300\n", EngineOptions->LLM_Timeout);
    printf("uciok\n");
}

void Uci_Loop(S_BOARD *pos, S_SEARCHINFO *info) {

	info->GAME_MODE = UCIMODE;

	setbuf(stdin, NULL);
    setbuf(stdout, NULL);

	char line[INPUTBUFFER];
	PrintUciInfo();
	
	int MB = 64;

	while (TRUE) {
		memset(&line[0], 0, sizeof(line));
        fflush(stdout);
        if (!fgets(line, INPUTBUFFER, stdin))
        continue;

        if (line[0] == '\n')
        continue;

        if (!strncmp(line, "isready", 7)) {
            printf("readyok\n");
            continue;
        } else if (!strncmp(line, "position", 8)) {
            ParsePosition(line, pos);
        } else if (!strncmp(line, "ucinewgame", 10)) {
            ParsePosition("position startpos\n", pos);
        } else if (!strncmp(line, "go", 2)) {
            printf("Seen Go..\n");
            ParseGo(line, info, pos);
        } else if (!strncmp(line, "quit", 4)) {
            info->quit = TRUE;
            break;
        } else if (!strncmp(line, "uci", 3)) {
            PrintUciInfo();
        } else if (!strncmp(line, "debug", 4)) {
            DebugAnalysisTest(pos,info);
            break;
        } else if (!strncmp(line, "setoption name Hash value ", 26)) {			
			sscanf(line,"%*s %*s %*s %*s %d",&MB);
			if(MB < 4) MB = 4;
			if(MB > MAX_HASH) MB = MAX_HASH;
			printf("Set Hash to %d MB\n",MB);
			InitHashTable(pos->HashTable, MB);
		} else if (!strncmp(line, "setoption name Book value ", 26)) {			
			char *ptrTrue = NULL;
			ptrTrue = strstr(line, "true");
			if(ptrTrue != NULL) {
				EngineOptions->UseBook = TRUE;
			} else {
				EngineOptions->UseBook = FALSE;
			}
		} else if (!strncmp(line, "setoption name LLM_Enabled value ", 33)) {
			if (strstr(line, "false") || strstr(line, "0") || strstr(line, "off")) {
				EngineOptions->LLM_Enabled = FALSE;
				printf("info string LLM_Enabled set to false\n");
			} else {
				EngineOptions->LLM_Enabled = TRUE;
				printf("info string LLM_Enabled set to true\n");
			}
		} else if (!strncmp(line, "setoption name LLM_Model value ", 31)) {
			char val[64] = {0};
			if (sscanf(line, "%*s %*s %*s %*s %63s", val) == 1) {
				snprintf(EngineOptions->LLM_Model, sizeof(EngineOptions->LLM_Model), "%s", val);
				printf("info string LLM_Model set to %s\n", EngineOptions->LLM_Model);
			}
		} else if (!strncmp(line, "setoption name LLM_Url value ", 29)) {
			char val[256] = {0};
			if (sscanf(line, "%*s %*s %*s %*s %255s", val) == 1) {
				if (strstr(val, "/api/generate")) {
					snprintf(EngineOptions->LLM_Url, sizeof(EngineOptions->LLM_Url), "%s", val);
				} else {
					snprintf(EngineOptions->LLM_Url, sizeof(EngineOptions->LLM_Url), "%s/api/generate", val);
				}
				printf("info string LLM_Url set to %s\n", EngineOptions->LLM_Url);
			}
		} else if (!strncmp(line, "setoption name LLM_Temperature value ", 37)) {
			float temp = 0.8f;
			if (sscanf(line, "%*s %*s %*s %*s %f", &temp) == 1) {
				EngineOptions->LLM_Temperature = temp;
				printf("info string LLM_Temperature set to %.2f\n", EngineOptions->LLM_Temperature);
			}
		} else if (!strncmp(line, "setoption name LLM_Constrained value ", 37)) {
			if (strstr(line, "false") || strstr(line, "0") || strstr(line, "off")) {
				EngineOptions->LLM_Constrained = FALSE;
				printf("info string LLM_Constrained set to false\n");
			} else {
				EngineOptions->LLM_Constrained = TRUE;
				printf("info string LLM_Constrained set to true\n");
			}
		} else if (!strncmp(line, "setoption name LLM_Timeout value ", 33)) {
			int timeout = 30;
			if (sscanf(line, "%*s %*s %*s %*s %d", &timeout) == 1) {
				if (timeout < 1) timeout = 1;
				EngineOptions->LLM_Timeout = timeout;
				printf("info string LLM_Timeout set to %d s\n", EngineOptions->LLM_Timeout);
			}
		}
		if(info->quit) break;
    }
}













