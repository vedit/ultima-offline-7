#pragma once
#include <string>
bool LocalCharacterPending();
std::string LocalCreateCharacter(int female, const std::string &encoded);
// Optional dream handoff. Ordinary BEGIN and saved games retain original placement.
bool LocalDreamBegin();
void LocalDreamArrival();
