using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using ASCloudModuleProbe;
public static class WineRunner {
 static string reportPath;
 static string Quote(string value) {
  var b=new StringBuilder("\"");
  foreach(char c in value) {
   if(c=='"' || c=='\\') { b.Append('\\');b.Append(c); }
   else if(c<32) { b.Append("\\u");b.Append(((int)c).ToString("x4")); }
   else b.Append(c);
  }
  return b.Append('"').ToString();
 }
 static string Json(object value) {
  if(value==null)return "null";
  if(value is string)return Quote((string)value);
  if(value is bool)return (bool)value?"true":"false";
  var dictionary=value as IDictionary;
  if(dictionary!=null) {
   var parts=new List<string>();
   foreach(DictionaryEntry entry in dictionary)parts.Add(Quote((string)entry.Key)+":"+Json(entry.Value));
   return "{"+String.Join(",",parts.ToArray())+"}";
  }
  var enumerable=value as IEnumerable;
  if(enumerable!=null) {
   var parts=new List<string>();foreach(object item in enumerable)parts.Add(Json(item));
   return "["+String.Join(",",parts.ToArray())+"]";
  }
  return Convert.ToString(value,CultureInfo.InvariantCulture);
 }
 public static void Save(Dictionary<string,object> value) {
  string pending=reportPath+".pending";
  File.WriteAllText(pending,Json(value),new UTF8Encoding(false));
  if(File.Exists(reportPath))File.Replace(pending,reportPath,null);
  else File.Move(pending,reportPath);
 }
 public static int Main(string[] args) {
  if(args.Length!=2)return 2;
  reportPath=Path.GetFullPath(args[0]);
  var report=new Dictionary<string,object>{{"probe_version","1.4"},{"result","worker_started"},
   {"phase","request_read"},{"tunnel_opened",false},{"video_validated",false}};
  int code=5;
  try {
   Save(report);
   Console.InputEncoding=new UTF8Encoding(false);
   string source=Console.ReadLine();string serial=Console.ReadLine();string portText=Console.ReadLine();
   ushort remote;
   if(String.IsNullOrEmpty(source) || !UInt16.TryParse(portText,out remote) || remote==0 ||
      serial==null || !System.Text.RegularExpressions.Regex.IsMatch(serial,@"\A[A-Za-z0-9_-]{4,99}\z"))
    throw new ArgumentException();
   report["phase"]="assembly_load";Save(report);
   var expected=new Dictionary<string,string> {
    {"libt2u.dll","528b8289c6f59e447c91508790d21abe888ad16ee1b1f6e30a52c4799bbf4d02"},
    {"Libt2uWrapper.dll","0dbef79ccdc2c0995c46eba337b20bb3d1d4567bb0480f535bfafbbf00aa31a6"},
    {"SIMNext.Core.dll","6c90f47a36ebaffaf47e8183e1f6177629761ac7d8622316dc08ea7cdc6d2612"},
    {"SIMNext.Model.dll","2e551cc790593b5661d5faf5520d99da563e46735a3cb9cc8b3fe164206e2881"},
    {"SIMNext.P2PSDK.dll","233c7dcb4c6f44965a36837cf60a150d0ae176f5cf3eaad47fb6500113a3f1a2"},
    {"NLog.dll","68936e2536bc04e0815fb9bee4c702adb989447d80b186a769fd68ee9899e13d"},
   };
   string stage=Path.Combine(Path.GetDirectoryName(reportPath),"staged");
   report=Loader.RunWithLoadedAdapter(source,stage,expected,
    delegate(Type adapter,Dictionary<string,object> value) {
     Initialization.RunWindowsTunnel(adapter,stage,serial,remote,Path.GetFullPath(args[1]),value,Save);
    });
   serial=null;
   report["execution_environment"]="wine";
   if((string)report["result"]=="tunnel_closed" && report.ContainsKey("cleanup_returned") &&
      (bool)report["cleanup_returned"])
    code=0;
  }catch(Exception e) {
   report["result"]="wine_runner_failed";
   var errors=new List<Dictionary<string,object>>();
   for(int i=0;e!=null && i<6;i++,e=e.InnerException)
    errors.Add(new Dictionary<string,object>{{"type",e.GetType().FullName},{"hresult",System.Runtime.InteropServices.Marshal.GetHRForException(e)}});
   report["errors"]=errors;
  }
  try { Save(report); } catch { code=6; }
  // Bound the lifetime even if an original worker thread survived partial initialization.
  Environment.Exit(code);
  return code;
 }
}
