#define _UNICODE
#include <windows.h>
#include <objbase.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
static wchar_t folder[32768];
static void marker(const wchar_t *name){wchar_t p[32768];swprintf(p,32768,L"%ls\\%ls",folder,name);HANDLE h=CreateFileW(p,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);if(h!=INVALID_HANDLE_VALUE)CloseHandle(h);}
static int marker_in(const wchar_t *dir,const wchar_t *name){wchar_t p[32768];swprintf(p,32768,L"%ls\\%ls",dir,name);HANDLE h=CreateFileW(p,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);if(h==INVALID_HANDLE_VALUE)return 0;CloseHandle(h);return 1;}
static BOOL WINAPI cancelled(DWORD type){marker(L"cancel");return FALSE;}
static int exists(const wchar_t *name){wchar_t p[32768];swprintf(p,32768,L"%ls\\%ls",folder,name);return GetFileAttributesW(p)!=INVALID_FILE_ATTRIBUTES;}
static void status(void){static char prev[8192]="";char buf[8192]={0};wchar_t p[32768];swprintf(p,32768,L"%ls\\status.txt",folder);FILE *f=_wfopen(p,L"rb");if(f){fread(buf,1,sizeof(buf)-1,f);fclose(f);if(strcmp(prev,buf)){printf("%s\n",buf);fflush(stdout);strcpy(prev,buf);}}}
static int waitfor(const wchar_t *name){ULONGLONG start=GetTickCount64();while(!exists(name)){status();if(exists(L"error"))return 0;if(GetTickCount64()-start>7200000){marker(L"cancel");puts("Sync timeout. Game not started / progress kept locally.");return 0;}if(!exists(L"status.txt")&&GetTickCount64()-start>45000){marker(L"cancel");puts("Sync worker unavailable. Check DSP-Sync installation.");return 0;}Sleep(1000);}status();return 1;}
static int quote(wchar_t *dst,size_t cap,const wchar_t *src){size_t n=0;dst[n++]=L'"';while(*src){size_t bs=0;while(*src==L'\\'){bs++;src++;}size_t count=(*src==L'"'||!*src)?bs*2:bs;if(n+count+3>=cap)return 0;while(count--)dst[n++]=L'\\';if(!*src)break;if(*src==L'"')dst[n++]=L'\\';dst[n++]=*src++;}dst[n++]=L'"';dst[n]=0;return 1;}
int wmain(int argc,wchar_t **argv){
 SetConsoleOutputCP(CP_UTF8);SetConsoleTitleW(L"戴森球计划 · Git 同步");
 if(argc<2||_wcsicmp(wcsrchr(argv[1],L'\\')?wcsrchr(argv[1],L'\\')+1:argv[1],L"DSPGAME.exe")){puts("Expected original DSPGAME.exe from Steam %command%.");return 2;}
 HANDLE mutex=CreateMutexW(NULL,TRUE,L"Local\\DSP-OneDrive-Steam-Sync");if(GetLastError()==ERROR_ALREADY_EXISTS){puts("DSP sync already running.");Sleep(4000);return 3;}
 wchar_t exe[32768],ini[32768],ipc[32768],cmd[32768],part[32768],cwd[32768],sid[64],path[32768];
 GetModuleFileNameW(NULL,exe,32768);*wcsrchr(exe,L'\\')=0;swprintf(ini,32768,L"%ls\\bridge.ini",exe);
 GetPrivateProfileStringW(L"bridge",L"ipc",L"",ipc,32768,ini);if(!*ipc){puts("Missing bridge.ini ipc path.");return 4;}
 GUID g;if(FAILED(CoCreateGuid(&g)))return 5;swprintf(sid,64,L"%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x",g.Data1,g.Data2,g.Data3,g.Data4[0],g.Data4[1],g.Data4[2],g.Data4[3],g.Data4[4],g.Data4[5],g.Data4[6],g.Data4[7]);
 CreateDirectoryW(ipc,NULL);swprintf(path,32768,L"%ls\\sessions",ipc);CreateDirectoryW(path,NULL);swprintf(folder,32768,L"%ls\\sessions\\%ls",ipc,sid);CreateDirectoryW(folder,NULL);SetConsoleCtrlHandler(cancelled,TRUE);
 swprintf(path,32768,L"%ls\\requests",ipc);CreateDirectoryW(path,NULL);swprintf(path,32768,L"%ls\\requests\\%ls.request",ipc,sid);HANDLE h=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);if(h==INVALID_HANDLE_VALUE)return 6;CloseHandle(h);
 GetPrivateProfileStringW(L"bridge",L"python",L"",part,32768,ini);
 if(*part){
  wchar_t python[32768],script[32768];wcscpy(python,part);
  GetPrivateProfileStringW(L"bridge",L"worker_script",L"",script,32768,ini);
  if(!*script||!quote(cmd,32768,python)||!quote(part,32768,script)||wcslen(cmd)+wcslen(part)+100>=32768){marker(L"cancel");return 7;}
  wcscat(cmd,L" -u ");wcscat(cmd,part);wcscat(cmd,L" --once ");wcscat(cmd,sid);
  STARTUPINFOW si={.cb=sizeof(si)};PROCESS_INFORMATION pi;
  if(!CreateProcessW(python,cmd,NULL,NULL,FALSE,CREATE_NO_WINDOW,NULL,exe,&si,&pi)){marker(L"cancel");puts("Failed to start sync worker.");Sleep(5000);return 7;}
  CloseHandle(pi.hThread);CloseHandle(pi.hProcess);
 }
 puts("Checking Git remote before game launch...");fflush(stdout);
 int offline=0;
 if(!waitfor(L"ready")){
  if(!exists(L"offline-allowed")){Sleep(10000);return 8;}
  int choice=MessageBoxW(NULL,L"启动前同步失败。具体原因见同步窗口。\n\n可以继续在本机离线游玩，但本次退出后不会自动上传。下次启动时会重新检查同步状态。\n\n是否离线启动游戏？",L"戴森球计划 · 同步失败",MB_YESNO|MB_ICONWARNING|MB_DEFBUTTON2|MB_SYSTEMMODAL);
  if(choice!=IDYES){Sleep(10000);return 8;}
  if(!marker_in(ipc,L"offline-pending")){puts("Could not record offline state; game not started.");Sleep(10000);return 12;}
  marker(L"offline");offline=1;
  puts("Launching offline. This session will not upload after exit.");fflush(stdout);
 }
 cmd[0]=0;for(int i=1;i<argc;i++){if(!quote(part,32768,argv[i])||wcslen(cmd)+wcslen(part)+2>=32768){marker(L"cancel");return 9;}if(i>1)wcscat(cmd,L" ");wcscat(cmd,part);}
 wcscpy(cwd,argv[1]);wchar_t *slash=wcsrchr(cwd,L'\\');if(slash)*slash=0;
 STARTUPINFOW si={.cb=sizeof(si)};PROCESS_INFORMATION pi;
 if(!CreateProcessW(argv[1],cmd,NULL,NULL,FALSE,0,NULL,slash?cwd:NULL,&si,&pi)){marker(L"cancel");printf("Game launch failed: %lu\n",GetLastError());Sleep(10000);return 10;}
 marker(L"started");puts(offline?"Game running offline; no upload will occur after exit.":"Game running. Sync will continue after exit.");fflush(stdout);WaitForSingleObject(pi.hProcess,INFINITE);CloseHandle(pi.hThread);CloseHandle(pi.hProcess);marker(L"exited");
 if(offline){puts("Offline game closed. Local progress was not uploaded.");fflush(stdout);Sleep(5000);ReleaseMutex(mutex);CloseHandle(mutex);return 0;}
 puts("Game closed. Waiting for upload...");fflush(stdout);int ok=waitfor(L"done");Sleep(ok?5000:15000);ReleaseMutex(mutex);CloseHandle(mutex);return ok?0:11;
}
