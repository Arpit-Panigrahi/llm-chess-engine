CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Wno-unused-parameter
LDFLAGS ?= -lcurl

SRCS = xboard.c vice.c uci.c evaluate.c pvtable.c init.c bitboards.c hashkeys.c \
       board.c data.c attack.c io.c movegen.c validate.c makemove.c perft.c \
       search.c misc.c polybook.c polykeys.c llm_search.c http_client.c \
       llm_parser.c telemetry.c cJSON.c

TARGET = vice

.PHONY: all debug clean

all: $(TARGET)

$(TARGET): $(SRCS)
	$(CC) $(CFLAGS) $(SRCS) -o $(TARGET) $(LDFLAGS)

debug: CFLAGS = -g -DDEBUG -Wall -Wextra -Wno-unused-parameter
debug: $(TARGET)

clean:
	rm -f $(TARGET) *.o