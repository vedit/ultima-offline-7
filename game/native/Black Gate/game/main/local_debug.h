#pragma once
#include <string>
#include <istream>
bool LocalDebugEnabled();
std::string LocalDebugSnapshot();
std::string LocalDebugCommand(const std::string &op,int a,int b,std::istream &input,bool idle,int sequence);
void LocalDebugReplay(int sequence);
void LocalDebugReset();
void LocalDebugFreed(short handle);
