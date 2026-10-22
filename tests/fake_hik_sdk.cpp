#include "HCNetSDK.h"
#include <cstring>
#include <cstdlib>
#include <fstream>
#include <vector>
static int file_count=0;
extern "C" int NET_DVR_Init(){return 1;}
extern "C" int NET_DVR_Cleanup(){return 1;}
extern "C" unsigned NET_DVR_GetLastError(){return 23;}
extern "C" int NET_DVR_SetConnectTime(unsigned timeout,unsigned tries){return tries==1;}
extern "C" int NET_DVR_SetReconnect(unsigned timeout,int enabled){return enabled==0;}
extern "C" int NET_DVR_Login_V40(NET_DVR_USER_LOGIN_INFO* p,NET_DVR_DEVICEINFO_V40* d){
 if(p->wPort!=8000 || p->bUseAsynLogin)return -1;
 if(std::strcmp(p->sUserName,"fail")==0)return -1;
 d->struDeviceV30.byChanNum=16;d->struDeviceV30.byStartChan=1;return 7;
}
extern "C" int NET_DVR_Logout(int user){return user==7;}
extern "C" int NET_DVR_FindFile_V40(int user,NET_DVR_FILECOND_V40* p){
 if(user!=7 || p->lChannel!=1 || p->dwFileType!=255)return -1;return 8;
}
extern "C" int NET_DVR_FindNextFile_V40(int handle,NET_DVR_FINDDATA_V40* p){
 if(file_count++)return 1003;
 memset(p,0,sizeof(*p));memcpy(p->sFileName,"private-name",12);
 p->struStartTime={2026,10,21,21,20,0};p->struStopTime={2026,10,21,21,25,0};p->dwFileSize=10000;return 1000;
}
extern "C" int NET_DVR_FindClose_V30(int handle){return handle==8;}
extern "C" int NET_DVR_RealPlay_V40(int user,NET_DVR_PREVIEWINFO* p,REALDATACALLBACK cb,void* opaque){
 if(user!=7 || p->lChannel!=1 || p->hPlayWnd)return -1;
 if(const char* path=std::getenv("ARTIN_TEST_VIDEO")){
  std::ifstream file(path,std::ios::binary);std::vector<unsigned char> media((std::istreambuf_iterator<char>(file)),{});
  if(media.size()<40)return -1;cb(9,1,media.data(),40,opaque);
  for(size_t i=40;i<media.size();i+=4096)cb(9,2,media.data()+i,(unsigned)std::min((size_t)4096,media.size()-i),opaque);
  return 9;
 }
 unsigned char data[1024]={0};cb(9,1,data,40,opaque);cb(9,2,data,1024,opaque);return 9;
}
extern "C" int NET_DVR_StopRealPlay(int handle){return handle==9;}
extern "C" int NET_DVR_PlayBackByTime_V40(int user,const NET_DVR_VOD_PARA* p){
 if(user!=7 || p->dwSize!=sizeof(*p) || p->struIDInfo.dwSize!=sizeof(NET_DVR_STREAM_INFO) || p->struIDInfo.dwChannel!=1 || p->hWnd || p->byDownload)return -1;
 return 10;
}
extern "C" int NET_DVR_SetPlayDataCallBack_V40(int handle,void(*cb)(int,unsigned,unsigned char*,unsigned,void*),void* opaque){
 if(const char* path=std::getenv("ARTIN_TEST_VIDEO")){
  std::ifstream file(path,std::ios::binary);std::vector<unsigned char> media((std::istreambuf_iterator<char>(file)),{});
  if(media.size()<40)return 0;cb(10,1,media.data(),40,opaque);
  for(size_t i=40;i<media.size();i+=4096)cb(10,2,media.data()+i,(unsigned)std::min((size_t)4096,media.size()-i),opaque);
  return handle==10;
 }
 unsigned char data[1024]={0};cb(10,1,data,40,opaque);cb(10,2,data,1024,opaque);return handle==10;
}
extern "C" int NET_DVR_PlayBackControl_V40(int handle,unsigned command,void* a,unsigned b,void* c,unsigned* d){
 if(handle==10 && command==13 && std::getenv("ARTIN_TEST_COMPLETE")){*(unsigned*)c=100;*d=4;return 1;}
 return handle==10 && (command==1 || command==3 || command==4 || command==5 || command==6 || command==7);
}
extern "C" int NET_DVR_StopPlayBack(int handle){return handle==10;}
