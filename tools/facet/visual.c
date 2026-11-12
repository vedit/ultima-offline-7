// ClassicUO's public x64 PluginHeader, through its SDL_Window field.
// Install and Tick run inside the opt-in disposable client on its game thread.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <stdbool.h>
#include <math.h>

typedef struct {
    int client_version;
    void *hwnd, *on_recv, *on_send, *hotkey, *mouse, *on_position, *closing;
    void *initialize, *connected, *disconnected, *focus_gained, *focus_lost;
    void *uo_path, *recv, *send, *packet_length;
    int (*position)(int *, int *, int *);
    void *cast_spell, *static_image;
    void (*tick)(void);
    int (*walk)(int, int);
    void *set_title, *on_recv_new, *on_send_new, *recv_new, *send_new, *draw, *window;
} PluginHeader;

// SDL 3.2 SDL_KeyboardEvent and SDL_Event (only key-up is submitted).
typedef union {
    struct {
        uint32_t type, reserved;
        uint64_t timestamp;
        uint32_t window_id, keyboard_id, scancode, key;
        uint16_t modifiers, raw;
        bool down, repeat;
    } keyboard;
    struct {
        uint32_t type, reserved;
        uint64_t timestamp;
        uint32_t window_id, mouse_id;
        uint8_t button, down, clicks, pad;
        float x, y;
    } mouse;
    unsigned char padding[128];
} Event;
_Static_assert(offsetof(PluginHeader, tick)==160 && offsetof(PluginHeader, window)==224, "ClassicUO x64 ABI");
_Static_assert(sizeof(Event)==128 && offsetof(Event,keyboard.key)==28,"SDL3 event ABI");

static int (*position)(int *, int *, int *);
static int (*walk)(int, int);
static bool (*push_event)(Event *);
static void (*warp)(void *,float,float);
static bool (*window_size)(void *,int *,int *);
static bool (*pixel_size)(void *,int *,int *);
static uint32_t (*mouse_state)(float *,float *);
static void *window;
static uint32_t window_id;
static ULONGLONG next_poll;
static const char *pending="../state/visual/request";
static const char *running="../state/visual/in-progress";

static struct {
    char id[33];
    float x,y;
    int button, remaining, sent;
    bool had_player;
} click;

static void finish(const char *id,const char *result,int x,int y,int z)
{
    FILE *out=fopen("../state/visual/reply.tmp","wb");
    if (out) {
        fprintf(out,"%s %s %lu %d %d %d\n",id,result,(unsigned long)GetCurrentProcessId(),x,y,z);
        if (fclose(out)==0) MoveFileExA("../state/visual/reply.tmp","../state/visual/reply",MOVEFILE_REPLACE_EXISTING);
    }
    DeleteFileA(running);
}

static void tick(void)
{
    ULONGLONG now=GetTickCount64();
    if (now<next_poll) return;
    next_poll=now+50;
    if (click.remaining) {
        int x=0,y=0,z=0;
        float mx=0,my=0;
        mouse_state(&mx,&my);
        bool has_player=position(&x,&y,&z)!=0;
        if (has_player!=click.had_player || fabsf(mx-click.x)>2 || fabsf(my-click.y)>2) {
            click.remaining=0;
            finish(click.id,"pointer-moved",x,y,z);
            return;
        }
        Event e={0};
        e.mouse.window_id=window_id;
        e.mouse.button=(uint8_t)click.button;
        e.mouse.clicks=(uint8_t)++click.sent;
        e.mouse.x=mx; e.mouse.y=my;
        e.mouse.type=0x401; e.mouse.down=1; push_event(&e);
        e.mouse.type=0x402; e.mouse.down=0; push_event(&e);
        if (--click.remaining==0) finish(click.id,has_player?"click-requested":"click-menu",x,y,z);
        next_poll=now+100;
        return;
    }
    if (!MoveFileA(pending,running)) return;
    char id[33]={0}, verb[16]={0}, extra;
    int arg=-1, x=0, y=0, z=0;
    FILE *in=fopen(running,"rb");
    int px=0, py=0, fw=0, fh=0;
    int fields=in ? fscanf(in,"%32[0123456789abcdef] %15s %d %d %d %d %d %c",
                           id,verb,&arg,&px,&py,&fw,&fh,&extra) : 0;
    if (in) fclose(in);
    const char *result="invalid";
    if ((fields==3 || fields==7) && strlen(id)==32) {
        bool has_player=position(&x,&y,&z)!=0;
        if (fields==3 && strcmp(verb,"capture")==0 && arg==0) {
            Event e={0};
            e.keyboard.type=0x301; // SDL_EVENT_KEY_UP
            e.keyboard.window_id=window_id;
            e.keyboard.scancode=70; // SDL_SCANCODE_PRINTSCREEN
            e.keyboard.key=0x40000000u | 70u;
            // The stock event filter handles this synchronously and can
            // consume it. The controller requires a newly written PNG.
            push_event(&e);
            result=has_player?"capture-requested":"capture-menu";
        } else if (fields==3 && strcmp(verb,"step")==0 && arg>=0 && arg<=7) {
            result=!has_player ? "outside-world" : walk(arg,0) ? "move-requested" : "move-rejected";
        } else if (fields==7 && strcmp(verb,"click")==0 && arg>=1 && arg<=3 &&
                   fw>0 && fh>0 && px>=0 && px<fw && py>=0 && py<fh) {
            int w=0,h=0,pw=0,ph=0;
            if (window_size(window,&w,&h) && w>0 && h>0 && pixel_size(window,&pw,&ph) && pw==fw && ph==fh) {
                float mx=(float)px*w/fw, my=(float)py*h/fh;
                warp(window,mx,my);
                memcpy(click.id,id,sizeof(id));
                click.x=mx; click.y=my;
                click.button=arg==3 ? 3 : 1;
                click.had_player=has_player;
                click.sent=0;
                click.remaining=arg==2 ? 2 : 1;
                next_poll=now+150;
                return;
            }
        }
    }
    finish(id,result,x,y,z);
}

__declspec(dllexport) void Install(PluginHeader *header)
{
    char enabled[2];
    if (GetEnvironmentVariableA("U7UO_VISUAL_TEST",enabled,2)!=1 || enabled[0]!='1') return;
    HMODULE sdl=GetModuleHandleW(L"SDL3.dll");
    if (!sdl || !header || !header->window || !header->position || !header->walk) return;
    uint32_t (*get_id)(void *)=(void *)GetProcAddress(sdl,"SDL_GetWindowID");
    push_event=(void *)GetProcAddress(sdl,"SDL_PushEvent");
    warp=(void *)GetProcAddress(sdl,"SDL_WarpMouseInWindow");
    window_size=(void *)GetProcAddress(sdl,"SDL_GetWindowSize");
    pixel_size=(void *)GetProcAddress(sdl,"SDL_GetWindowSizeInPixels");
    mouse_state=(void *)GetProcAddress(sdl,"SDL_GetMouseState");
    window=header->window;
    if (!get_id || !push_event || !warp || !window_size || !pixel_size || !mouse_state || !(window_id=get_id(window))) return;
    position=header->position;
    walk=header->walk;
    header->tick=tick;
}
