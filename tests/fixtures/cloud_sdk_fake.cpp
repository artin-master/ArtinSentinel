// Offline SDK double. Used signatures/layout are from Linux NetSDK 3.050.
// No sockets and no vendor binaries. All media is a local synthetic fixture.
#include <atomic>
#include <cstring>
#include <cstdlib>
#include <cstdio>
#include <csignal>
#include <fstream>
#include <thread>
#include <vector>
#include <unistd.h>
struct Info {
    unsigned char serial[48];
    int alarms_in, alarms_out, disks, type, channels;
    unsigned char limit, remaining, aligned[2];
    int lock;
    char reserved[24];
};
static_assert(sizeof(Info) == 100);
static_assert(sizeof(long) == 8);
using Callback = void(*)(long, unsigned, unsigned char*, unsigned, long, long);
static std::thread sender;
static std::atomic<bool> stopped{false};
static std::atomic<bool> paused{false};
static bool scenario(const char* name) {
    const char* value = std::getenv("FAKE_SCENARIO");
    return value && !std::strcmp(value, name);
}
static void trace(const char* text) {
    std::ofstream out(std::getenv("FAKE_TRACE"), std::ios::app);
    out << text << '\n';
}
extern "C" int CLIENT_Init(void*, long) {trace("init"); return 1;}
extern "C" void CLIENT_SetConnectTime(int ms, int count) {if(ms!=8000 || count!=1)std::_Exit(91);}
extern "C" unsigned CLIENT_GetSDKVersion() {return 0x0216a62d;}
extern "C" unsigned CLIENT_GetLastError() {return 0x80000064;}
extern "C" long CLIENT_LoginEx2(const char* host, unsigned short port, const char* user,
        const char* password, int mode, void* cap, Info* info, int* error) {
    trace("login");
    if(std::strcmp(host,std::getenv("FAKE_EXPECT_HOST") ? std::getenv("FAKE_EXPECT_HOST") : "127.0.0.1") || port!=(std::getenv("FAKE_EXPECT_PORT") ? std::atoi(std::getenv("FAKE_EXPECT_PORT")) : 55162) || mode!=(std::getenv("FAKE_EXPECT_MODE") ? std::atoi(std::getenv("FAKE_EXPECT_MODE")) : 19) || cap ||
       std::strcmp(user,"TEST-USER-PRIVATE") || std::strcmp(password,"TEST-PASSWORD-PRIVATE"))std::_Exit(92);
    std::puts("TEST-PASSWORD-PRIVATE SDK native noise");
    if(scenario("crash"))std::raise(SIGSEGV);
    if(scenario("hang_login"))sleep(4);
    if(scenario("password")){*error=1; return 0;}
    std::memset(info,0,sizeof(*info));
    std::strcpy(reinterpret_cast<char*>(info->serial),"TEST-SERIAL-PRIVATE");
    info->channels=4;
    return 0x123456789L;
}
extern "C" int CLIENT_Logout(long login) {if(login!=0x123456789L)std::_Exit(93);trace("logout");return 1;}
extern "C" void CLIENT_Cleanup() {trace("cleanup");if(scenario("hang_cleanup"))sleep(10);}
extern "C" long CLIENT_RealPlayEx(long login,int channel,void* window,int type) {
    if(login!=0x123456789L || channel!=0 || window || (std::getenv("FAKE_EXPECT_STREAM") ? type!=std::atoi(std::getenv("FAKE_EXPECT_STREAM")) : (type!=2 && type!=3)))std::_Exit(94);
    trace("realplay");return 0x23456789aL;
}
extern "C" int CLIENT_SetRealDataCallBackEx2(long handle,Callback cb,long user,unsigned flag) {
    if(handle!=0x23456789aL || user || flag!=1)std::_Exit(95);
    sender=std::thread([cb,handle]{
        std::ifstream in(std::getenv("FAKE_PAYLOAD"),std::ios::binary);
        std::vector<unsigned char> data((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
        if(data.empty())std::_Exit(96);
        while(!stopped){cb(handle,0,data.data(),data.size(),0,0);usleep(200000);}
    });return 1;
}
extern "C" int CLIENT_StopRealPlayEx(long handle) {
    if(handle!=0x23456789aL)std::_Exit(97);
    stopped=true;if(sender.joinable())sender.join();trace("stop");return 1;
}

struct NetTime {unsigned year,month,day,hour,minute,second;};
struct RecordInfo {unsigned channel;char filename[124];unsigned frames,size;NetTime start,end;unsigned drive,cluster;unsigned char kind,important,hint,stream;};
static_assert(sizeof(RecordInfo)==196);
extern "C" int CLIENT_QueryRecordFile(long login,int channel,int type,NetTime* start,NetTime* end,char* card,RecordInfo* out,int maxlen,int* count,int wait,int bytime){
 if(login!=0x123456789L || channel!=0 || type || card || maxlen!=300*196 || wait!=5000 || bytime)std::_Exit(98);
 *count=2;std::memset(out,0,2*sizeof(RecordInfo));out[0].channel=0;out[0].size=1;
 out[0].start={2026,10,19,8,10,0};out[0].end={2026,10,19,8,20,0};
 out[1]=out[0];out[1].channel=9;return 1;
}

using PlaybackCallback=int(*)(long,unsigned,unsigned char*,unsigned,long);
extern "C" long CLIENT_PlayBackByTimeEx(long login,int channel,NetTime* begin,NetTime* end,void* window,void* progress,long posuser,PlaybackCallback cb,long user){
 if(login!=0x123456789L || channel || window || progress || posuser || user || begin->year!=2026 || end->hour!=9)std::_Exit(99);
 trace("playback");sender=std::thread([cb]{std::ifstream in(std::getenv("FAKE_PAYLOAD"),std::ios::binary);std::vector<unsigned char> data((std::istreambuf_iterator<char>(in)),{});while(!stopped){if(!paused){const char* flag=std::getenv("FAKE_PLAYBACK_SMALL_CHUNKS");if(flag){for(size_t offset=0;offset<data.size()&&!stopped;offset+=512){while(paused&&!stopped)usleep(1000);if(!stopped)cb(0x23456789aL,0,data.data()+offset,std::min(size_t(512),data.size()-offset),0);if(const char* delay=std::getenv("FAKE_PLAYBACK_PACKET_DELAY_US"))usleep(std::atoi(delay));}}else cb(0x23456789aL,0,data.data(),data.size(),0);}usleep(200000);}});return 0x23456789aL;
}
extern "C" int CLIENT_StopPlayBack(long handle){trace("playback_stop");return CLIENT_StopRealPlayEx(handle);}

extern "C" int CLIENT_SetPlayBackSpeed(long handle,int speed){
 if(handle!=0x23456789aL)std::_Exit(100);
 char text[64];std::snprintf(text,sizeof(text),"speed=%d",speed);trace(text);
 return scenario("speed_rejected") ? 0 : 1;
}

extern "C" int CLIENT_PausePlayBack(long handle,int value){paused=value!=0;trace(value?"pause":"resume");return 1;}
