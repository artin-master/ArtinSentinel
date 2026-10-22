// Disposable initialization probe. No serial, account token or DVR login.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace ASCloudModuleProbe {
    public interface ITransportStatus { int GetStatus(); }

    public sealed class SimRunningException : Exception { }

    public sealed class WindowsTransportStatus : ITransportStatus {
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        private delegate int StatusFunction();
        [DllImport("kernel32.dll", EntryPoint="LoadLibraryExW", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern IntPtr LoadLibraryEx(string path, IntPtr reserved, uint flags);
        [DllImport("kernel32.dll", CharSet=CharSet.Ansi, ExactSpelling=true, SetLastError=true)]
        private static extern IntPtr GetProcAddress(IntPtr module, string name);
        [DllImport("kernel32.dll", EntryPoint="GetModuleFileNameW", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern uint GetModuleFileName(IntPtr module, StringBuilder path, uint capacity);
        private readonly IntPtr module;
        private readonly StatusFunction status;

        public static bool SimRunning() {
            Process[] processes = Process.GetProcessesByName("SIMNext");
            try { return processes.Length != 0; }
            finally { foreach (Process p in processes) p.Dispose(); }
        }

        public WindowsTransportStatus(string stage) {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT || IntPtr.Size != 8)
                throw new PlatformNotSupportedException();
            if (SimRunning()) throw new SimRunningException();
            string path = Path.GetFullPath(Path.Combine(stage, "libt2u.dll"));
            // LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32.
            // No global search-path or security-policy changes.
            module = LoadLibraryEx(path, IntPtr.Zero, 0x00000100 | 0x00000800);
            if (module == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            var actual = new StringBuilder(1024);
            uint count = GetModuleFileName(module, actual, (uint)actual.Capacity);
            if (count == 0 || count >= actual.Capacity || !String.Equals(
                    Path.GetFullPath(actual.ToString()), path, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException();
            IntPtr address = GetProcAddress(module, "t2u_status");
            if (address == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            status = (StatusFunction)Marshal.GetDelegateForFunctionPointer(address, typeof(StatusFunction));
            // Keep this module loaded until the disposable process ends. Do not
            // FreeLibrary while original callbacks/threads could still reference it.
        }

        public int GetStatus() {
            if (module == IntPtr.Zero) throw new InvalidOperationException();
            if (SimRunning()) throw new SimRunningException();
            return status();
        }
    }

    public static class Initialization {
        private static void Capture(Dictionary<string, object> report, Exception error) {
            var errors = report["errors"] as List<Dictionary<string, object>>;
            for (int i=0; error != null && i<6; i++, error=error.InnerException) {
                var entry = new Dictionary<string, object> {
                    {"type", error.GetType().FullName}, {"hresult", System.Runtime.InteropServices.Marshal.GetHRForException(error)}
                };
                var native = error as Win32Exception;
                if (native != null) entry["win32"] = native.NativeErrorCode;
                if (error is SimRunningException) report["sim_detected_during_probe"] = true;
                errors.Add(entry);
            }
        }

        private static void Publish(Dictionary<string, object> report, string phase,
                                    Action<Dictionary<string, object>> progress, Stopwatch clock) {
            report["phase"] = phase;
            report["elapsed_ms"] = clock.ElapsedMilliseconds;
            try { if (progress != null) progress(report); }
            catch {
                report["progress_write_failed"] = true;
                report["result"] = "diagnostic_write_failed";
            }
        }

        public static void RunWindows(Type adapter, string stage, Dictionary<string, object> report,
                                      Action<Dictionary<string, object>> progress) {
            if (WindowsTransportStatus.SimRunning()) {
                report["result"] = "sim_running";
                report["sim_detected_during_probe"] = true;
                return;
            }
            Run(adapter, delegate { return new WindowsTransportStatus(stage); }, report, progress, 15000);
        }

        public static void RunWindowsTunnel(Type adapter, string stage, string serial, ushort remote, string stopPath,
            Dictionary<string, object> report, Action<Dictionary<string, object>> progress) {
            if (WindowsTransportStatus.SimRunning()) { report["result"]="sim_running"; return; }
            Run(adapter, delegate { return new WindowsTransportStatus(stage); }, report, progress, 15000,
                delegate(object instance, Dictionary<string,object> value) {
                    Tunnel.Run(instance, new WindowsTunnelStatus(stage), serial, remote, value, progress, 10000, 0, 0, delegate { return File.Exists(stopPath); });
                });
        }

        public static void Run(Type adapter, Func<ITransportStatus> openNative,
                               Dictionary<string, object> report,
                               Action<Dictionary<string, object>> progress, int waitMilliseconds, Action<object, Dictionary<string, object>> ready = null) {
            if (!report.ContainsKey("errors")) report["errors"] = new List<Dictionary<string, object>>();
            report["probe_version"] = "1.4";
            report["result"] = "initialization_in_progress";
            report["constructor_invoked"] = false;
            report["constructor_returned"] = false;
            report["cleanup_attempted"] = false;
            report["cleanup_returned"] = false;
            report["transport_ready_observed"] = false;
            report["transport_validated"] = false;
            report["tunnel_opened"] = false;
            report["account_authentication_tested"] = false;
            report["services_mode"] = "null_optional_services";
            report["progress_write_failed"] = false;
            var history = new List<Dictionary<string, object>>();
            report["status_history"] = history;
            var clock = Stopwatch.StartNew();
            object instance = null;
            MethodInfo cleanup = null;
            ITransportStatus native = null;
            bool invoked = false;
            bool returned = false;
            try {
                if (waitMilliseconds < 1 || waitMilliseconds > 30000) throw new ArgumentOutOfRangeException();
                ConstructorInfo selected = null;
                foreach (ConstructorInfo ctor in adapter.GetConstructors(
                        BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)) {
                    ParameterInfo[] args = ctor.GetParameters();
                    if (args.Length == 2 &&
                        args[0].ParameterType.FullName == "SIMNext.Core.Service.ITelemetryReportService" &&
                        args[1].ParameterType.FullName == "SIMNext.Core.Service.ISystemSettingsService") {
                        if (selected != null) throw new AmbiguousMatchException();
                        selected = ctor;
                    }
                }
                cleanup = adapter.GetMethod("Cleanup", BindingFlags.Public | BindingFlags.Instance,
                                            null, Type.EmptyTypes, null);
                if (selected == null || cleanup == null || cleanup.ReturnType != typeof(void)) {
                    report["result"] = "unsupported_contract";
                    return;
                }
                Publish(report, "native_setup_started", progress, clock);
                native = openNative();
                Publish(report, "native_setup_returned", progress, clock);
                invoked = true;
                report["constructor_invoked"] = true;
                Publish(report, "constructor_started", progress, clock);
                // Original IL stores these services without invoking them in the
                // constructor. Telemetry callbacks guard null. No fake account,
                // settings, key, credential, or authentication outcome is supplied.
                instance = selected.Invoke(new object[] { null, null });
                returned = true;
                report["constructor_returned"] = true;
                Publish(report, "constructor_returned", progress, clock);
                var wait = Stopwatch.StartNew();
                int previous = Int32.MinValue;
                report["result"] = "initialization_not_ready";
                do {
                    int value = native.GetStatus();
                    if (value != previous) {
                        history.Add(new Dictionary<string, object> {
                            {"ms", clock.ElapsedMilliseconds}, {"value", value}
                        });
                        previous = value;
                    }
                    report["last_transport_status"] = value;
                    Publish(report, "transport_status", progress, clock);
                    if (value == 1) {
                        report["transport_ready_observed"] = true;
                        report["result"] = "initialization_ready";
                        break;
                    }
                    Thread.Sleep(100);
                } while (wait.ElapsedMilliseconds < waitMilliseconds);
                if ((string)report["result"] == "initialization_ready" && ready != null) ready(instance, report);
            } catch (Exception error) {
                report["result"] = !invoked ? "native_setup_failed" :
                    (!returned ? "constructor_failed_cleanup_unconfirmed" : "initialization_failed");
                Capture(report, error);
                Publish(report, "initialization_error", progress, clock);
            } finally {
                if (returned && instance != null) {
                    report["cleanup_attempted"] = true;
                    Publish(report, "cleanup_started", progress, clock);
                    try {
                        cleanup.Invoke(instance, null);
                        report["cleanup_returned"] = true;
                        Publish(report, "cleanup_returned", progress, clock);
                    } catch (Exception error) {
                        report["result"] = "cleanup_failed";
                        Capture(report, error);
                        Publish(report, "cleanup_error", progress, clock);
                    }
                }
                // Never call Cleanup/t2u_exit on an object whose constructor
                // failed partway: the last native operation is unknown. End the
                // disposable process instead and report cleanup as unconfirmed.
                GC.KeepAlive(instance);
                GC.KeepAlive(native);
                if ((bool)report["progress_write_failed"]) report["result"] = "diagnostic_write_failed";
                Publish(report, "finished", progress, clock);
            }
        }
    }
}
