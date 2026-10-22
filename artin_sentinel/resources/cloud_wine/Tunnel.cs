using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading;
namespace ASCloudModuleProbe {
 public interface ITunnelStatus { int GetPortStatus(ushort port); }
 public sealed class WindowsTunnelStatus : ITunnelStatus {
  [System.Runtime.InteropServices.UnmanagedFunctionPointer(System.Runtime.InteropServices.CallingConvention.Cdecl)]
  delegate int PortStatus(ushort port,IntPtr information);
  [System.Runtime.InteropServices.DllImport("kernel32.dll",EntryPoint="GetModuleHandleW",CharSet=System.Runtime.InteropServices.CharSet.Unicode)]
  static extern IntPtr GetModuleHandle(string name);
  [System.Runtime.InteropServices.DllImport("kernel32.dll",CharSet=System.Runtime.InteropServices.CharSet.Ansi,ExactSpelling=true)]
  static extern IntPtr GetProcAddress(IntPtr module,string name);
  readonly PortStatus status;
  public WindowsTunnelStatus(string stage) {
   IntPtr module=GetModuleHandle(System.IO.Path.GetFullPath(System.IO.Path.Combine(stage,"libt2u.dll")));
   if(module==IntPtr.Zero) throw new InvalidOperationException();
   IntPtr address=GetProcAddress(module,"t2u_port_status");
   if(address==IntPtr.Zero) throw new InvalidOperationException();
   status=(PortStatus)System.Runtime.InteropServices.Marshal.GetDelegateForFunctionPointer(address,typeof(PortStatus));
  }
  public int GetPortStatus(ushort port) {
   if(WindowsTransportStatus.SimRunning()) throw new SimRunningException();
   // The verified native implementation accepts NULL; no guessed output structure.
   return status(port,IntPtr.Zero);
  }
 }
 public static class Tunnel {
  static void Publish(Dictionary<string,object> r,string phase,Action<Dictionary<string,object>> progress) {
   r["phase"]=phase;
   if(progress!=null) progress(r);
  }
  public static void Run(object adapter,ITunnelStatus native,string serial,ushort remote,
      Dictionary<string,object> r,Action<Dictionary<string,object>> progress,int waitMs,int holdMs, ushort requestedLocalPort = 0, Func<bool> stopRequested = null) {
   r["tunnel_opened"]=false; r["video_validated"]=false; r["dvr_login_tested"]=false;
   r["result"]="invalid_input";
   if(serial==null || !Regex.IsMatch(serial,@"\A[A-Za-z0-9_-]{4,99}\z") || remote==0 ||
      waitMs<1 || waitMs>20000 || holdMs<0 || holdMs>300000) return;
   var history=new List<Dictionary<string,object>>(); r["tunnel_status_history"]=history;
   try {
    MethodInfo method=adapter.GetType().GetMethod("AddSDKPort",new Type[]{typeof(long),typeof(string),typeof(ushort),typeof(ushort)});
    if(method==null || method.ReturnType!=typeof(int)) {r["result"]="unsupported_tunnel_contract";return;}
    if(stopRequested!=null && stopRequested()){r["result"]="cancelled";return;}
    Publish(r,"add_sdk_port_started",progress);
    // deviceId is a private bookkeeping ID within this new adapter instance.
    // Use the original wrapper for its transport configuration, without extracting it.
    int port=(int)method.Invoke(adapter,new object[]{(long)1,serial,remote,requestedLocalPort});
    r["add_sdk_port_return"]=port;
    if(port<1 || port>65535){r["result"]="tunnel_open_failed";return;}
    if(requestedLocalPort!=0 && port!=requestedLocalPort){r["result"]="unexpected_local_port";return;}
    r["local_port"]=port;
    r["requested_local_port"]=(int)requestedLocalPort;
    var timer=Stopwatch.StartNew(); int previous=Int32.MinValue; int state=0;
    do {
     if(stopRequested!=null && stopRequested()){r["result"]="cancelled";return;}
     state=native.GetPortStatus((ushort)port);
     r["last_tunnel_status"]=state;
     if(state!=previous){history.Add(new Dictionary<string,object>{{"ms",timer.ElapsedMilliseconds},{"value",state}});previous=state;}
     Publish(r,"tunnel_status",progress);
     if(state==1 || state<0)break;
     Thread.Sleep(100);
    }while(timer.ElapsedMilliseconds<waitMs);
    if(state!=1){r["result"]="tunnel_not_ready";return;}
    r["tunnel_opened"]=true; r["result"]="tunnel_ready_observed";
    Publish(r,"tunnel_hold",progress);
    timer.Restart();
    do {
     if(stopRequested!=null && stopRequested()){r["result"]="tunnel_closed";return;}
     Thread.Sleep(100);
     state=native.GetPortStatus((ushort)port);r["last_tunnel_status"]=state;
     if(state!=1){r["result"]="tunnel_lost";return;}
    }while(holdMs==0 || timer.ElapsedMilliseconds<holdMs);
    r["hold_completed"]=true;
   }catch(Exception e){
    r["result"]="tunnel_probe_failed";
    var errors=new List<Dictionary<string,object>>();
    for(int i=0;e!=null && i<6;i++,e=e.InnerException)
     errors.Add(new Dictionary<string,object>{{"type",e.GetType().FullName},{"hresult",System.Runtime.InteropServices.Marshal.GetHRForException(e)}});
    r["errors"]=errors;
   }
  }
 }
}
