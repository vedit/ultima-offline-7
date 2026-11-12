#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"

typedef struct {
    lua_State *L;
    const char *source, *adapter, *reply;
    size_t source_len, adapter_len, reply_len, used;
    int id, event, item, resume_ref, ticks;
} Dialogue;

static void *bounded_alloc(void *p, void *ptr, size_t old, size_t n) {
    Dialogue *d = p;
    if (!ptr) old = 0;
    if (!n) { free(ptr); d->used -= old; return NULL; }
    if (n > (32u << 20) - (d->used - old)) return NULL;
    void *next = realloc(ptr, n);
    if (next) d->used = d->used - old + n;
    return next;
}
static Dialogue *owner(lua_State *L) {
    void *p; lua_getallocf(L, &p); return p;
}
static void budget(lua_State *L, lua_Debug *ar) {
    (void)ar;
    if (--owner(L)->ticks <= 0) luaL_error(L, "Dialogue host instruction budget exhausted");
}
static void chunk(lua_State *L, const char *s, size_t n, const char *label) {
    if (luaL_loadbufferx(L, s, n, label, "t") != LUA_OK) lua_error(L);
    lua_call(L, 0, 1);
}
static int setup(lua_State *L) {
    Dialogue *d = owner(L);
    const luaL_Reg libs[] = {{"_G",luaopen_base},{"table",luaopen_table},{"string",luaopen_string},
                             {"math",luaopen_math},{"coroutine",luaopen_coroutine},{"utf8",luaopen_utf8},{NULL,NULL}};
    for (const luaL_Reg *r = libs; r->func; ++r) {
        luaL_requiref(L, r->name, r->func, 1); lua_pop(L,1);
    }
    const char *remove[] = {"load","loadfile","dofile","print","warn","collectgarbage",NULL};
    for (const char **s = remove; *s; ++s) {lua_pushnil(L); lua_setglobal(L,*s);}
    lua_getglobal(L,"math");
    lua_pushnil(L); lua_setfield(L,-2,"random"); lua_pushnil(L); lua_setfield(L,-2,"randomseed"); lua_pop(L,1);
    chunk(L, d->adapter, d->adapter_len, "@dialogue-bridge");
    chunk(L, d->source, d->source_len, "@source-dialogue");
    lua_pushinteger(L,d->id); lua_pushinteger(L,d->event); lua_pushinteger(L,d->item);
    lua_call(L,4,1);
    if (!lua_isfunction(L,-1)) return luaL_error(L,"Invalid dialogue module");
    d->resume_ref = luaL_ref(L,LUA_REGISTRYINDEX);
    return 0;
}
static int resume(lua_State *L) {
    Dialogue *d = owner(L);
    lua_rawgeti(L,LUA_REGISTRYINDEX,d->resume_ref);
    // Replies use a private length-delimited tagged representation, never Lua source.
    if (!d->reply_len) return luaL_error(L,"Malformed empty reply");
    const char *p = d->reply;
    switch (p[0]) {
        case 'n': if(d->reply_len != 1) return luaL_error(L,"Invalid nil reply"); lua_pushnil(L); break;
        case 'i': {
            int64_t value;
            if(d->reply_len != 1 + sizeof(value)) return luaL_error(L,"Invalid integer reply");
            memcpy(&value,p+1,sizeof(value)); lua_pushinteger(L,value); break;
        }
        case 's': lua_pushlstring(L,p+1,d->reply_len-1); break;
        case 'a': {
            size_t size = d->reply_len - 1;
            if (size % sizeof(int64_t) || size > 4096 * sizeof(int64_t))
                return luaL_error(L,"Invalid integer array reply");
            int count = (int)(size / sizeof(int64_t));
            lua_createtable(L,count,0);
            for (int i=0;i<count;++i) {
                int64_t value;
                memcpy(&value,p+1+i*sizeof(value),sizeof(value));
                lua_pushinteger(L,value);
                lua_rawseti(L,-2,i+1);
            }
            break;
        }
        default: return luaL_error(L,"Unsupported host reply type");
    }
    lua_call(L,1,1);
    return 1;
}
static void message(lua_State *L, char *out, int cap) {
    const char *err = lua_type(L,-1) == LUA_TSTRING ? lua_tostring(L,-1) : "Lua dialogue failed";
    snprintf(out,(size_t)cap,"%s",err);
}
__declspec(dllexport) void u7_dialog_close(Dialogue *d) {
    if (d) { if(d->L) lua_close(d->L); free(d); }
}
__declspec(dllexport) Dialogue *u7_dialog_open(const char *source, int n, const char *adapter, int m,
                                                int id, int event, int item, char *error, int cap) {
    if (!source || !adapter || n<1 || n>(8<<20) || m<1 || m>65536 || !error || cap<2) return NULL;
    Dialogue *d = calloc(1,sizeof(*d));
    if (!d) return NULL;
    d->source=source; d->source_len=n; d->adapter=adapter; d->adapter_len=m;
    d->id=id; d->event=event; d->item=item; d->ticks=10000;
    d->L = lua_newstate(bounded_alloc,d);
    if (!d->L) {free(d); return NULL;}
    lua_sethook(d->L,budget,LUA_MASKCOUNT,1000);
    lua_pushcfunction(d->L,setup);
    if (lua_pcall(d->L,0,0,0) != LUA_OK) {message(d->L,error,cap); u7_dialog_close(d); return NULL;}
    d->source=NULL; d->adapter=NULL; return d;
}
__declspec(dllexport) int u7_dialog_next(Dialogue *d, const char *reply, int n, char *out, int cap) {
    if (!d || !reply || n<1 || n>65537 || !out || cap<2) return -1;
    lua_State *L = d->L;
    d->reply=reply; d->reply_len=n; d->ticks=1000;
    lua_pushcfunction(L,resume);
    int status = lua_pcall(L,0,1,0);
    d->reply=NULL;
    if (status != LUA_OK) {message(L,out,cap); lua_pop(L,1); return -1;}
    size_t size=0;
    const char *s = lua_tolstring(L,-1,&size);
    if(!s || size >= (size_t)cap) {
        snprintf(out,(size_t)cap,"Invalid or oversized dialogue record"); lua_pop(L,1); return -1;
    }
    memcpy(out,s,size); lua_pop(L,1); return (int)size;
}
