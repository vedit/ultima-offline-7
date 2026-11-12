/* ABI 1: run a generated text chunk as function(event, flags). No Lua libraries opened. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lua.h"
#include "lauxlib.h"

#define FLAG_COUNT 32768
#define MEMORY_LIMIT (4u * 1024u * 1024u)

typedef struct {
    const char *source;
    size_t length;
    size_t used;
    int event;
    int line;
    unsigned char *flags;
} Invocation;

static void *allocate(void *context, void *ptr, size_t old_size, size_t new_size) {
    Invocation *call = context;
    if (!ptr) old_size = 0;  /* Lua can pass a type tag for a new allocation. */
    if (new_size == 0) {
        free(ptr);
        call->used -= old_size;
        return NULL;
    }
    if (new_size > MEMORY_LIMIT - (call->used - old_size)) return NULL;
    void *next = realloc(ptr, new_size);
    if (next) call->used = call->used - old_size + new_size;
    return next;
}

static Invocation *context(lua_State *L) {
    void *call;
    lua_getallocf(L, &call);
    return call;
}

static int flag_index(lua_State *L) {
    lua_Integer i = luaL_checkinteger(L, 2);
    if (i < 0 || i >= FLAG_COUNT) luaL_error(L, "global flag index outside host range");
    return (int)i;
}

static int read_flag(lua_State *L) {
    lua_pushinteger(L, context(L)->flags[flag_index(L)]);
    return 1;
}

static int write_flag(lua_State *L) {
    int i = flag_index(L);
    lua_Integer value = luaL_checkinteger(L, 3);
    if (value != 0 && value != 1) return luaL_error(L, "global flag must be 0 or 1");
    context(L)->flags[i] = (unsigned char)value;
    return 0;
}

static void execution_hook(lua_State *L, lua_Debug *ar) {
    if (ar->event == LUA_HOOKCOUNT) luaL_error(L, "Usecode instruction budget exhausted");
    else context(L)->line = ar->currentline;
}

static int invoke(lua_State *L) {
    Invocation *call = context(L);
    if (luaL_loadbufferx(L, call->source, call->length, "@function.lua", "t") != LUA_OK)
        return lua_error(L);
    lua_call(L, 0, 1);
    if (!lua_isfunction(L, -1)) return luaL_error(L, "compiled chunk must return a function");
    lua_pushinteger(L, call->event);
    lua_newuserdatauv(L, 1, 0);
    lua_createtable(L, 0, 2);
    lua_pushcfunction(L, read_flag);
    lua_setfield(L, -2, "__index");
    lua_pushcfunction(L, write_flag);
    lua_setfield(L, -2, "__newindex");
    lua_setmetatable(L, -2);
    lua_call(L, 2, 0);
    return 0;
}

__declspec(dllexport) int u7_run_v1(const char *source, int length, int event,
    unsigned char *flags, int flag_count, int budget, char *error, int capacity, int *line) {
    if (!source || length < 1 || length > 1048576 || !flags || flag_count != FLAG_COUNT ||
        budget < 1 || budget > 1000000 || !line || !error || capacity < 2) return -1;
    Invocation call = {.source = source, .length = (size_t)length, .event = event, .flags = flags};
    lua_State *L = lua_newstate(allocate, &call);
    if (!L) return -1;
    lua_sethook(L, execution_hook, LUA_MASKLINE | LUA_MASKCOUNT, budget);
    lua_pushcfunction(L, invoke);
    int status = lua_pcall(L, 0, 0, 0);
    if (status != LUA_OK) {
        const char *message = lua_type(L, -1) == LUA_TSTRING ? lua_tostring(L, -1) : NULL;
        snprintf(error, (size_t)capacity, "%s", message ? message : "Lua execution failed");
    }
    *line = call.line;
    lua_close(L);
    return status;
}
