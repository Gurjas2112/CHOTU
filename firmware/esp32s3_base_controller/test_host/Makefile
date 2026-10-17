# Host-side unit tests for the firmware logic (Windows MSYS2 g++, Linux, macOS)
#   make -C firmware/esp32s3_base_controller/test_host
CXX ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Werror -I../lib/chotu_logic/src

ifeq ($(OS),Windows_NT)
  EXE := test_chotu_logic.exe
else
  EXE := test_chotu_logic
endif

all: run

$(EXE): test_chotu_logic.cpp ../lib/chotu_logic/src/chotu_logic.h
	$(CXX) $(CXXFLAGS) test_chotu_logic.cpp -o $(EXE)

run: $(EXE)
	./$(EXE)

clean:
	rm -f test_chotu_logic test_chotu_logic.exe

.PHONY: all run clean
