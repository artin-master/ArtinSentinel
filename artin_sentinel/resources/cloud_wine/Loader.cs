// Disposable loader. Optional callback executes only after verified loading.
using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.RegularExpressions;

namespace ASCloudModuleProbe {
    public static class Loader {
        private static string Digest(string path) {
            using (var input = File.OpenRead(path))
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(input)).Replace("-", "").ToLowerInvariant();
        }

        private static string SafeName(string value) {
            try {
                string name = new AssemblyName(value).Name;
                if (Regex.IsMatch(name ?? "", @"\A[A-Za-z0-9_.-]{1,150}\z")) return name;
            } catch { }
            return "unidentified";
        }

        public static Dictionary<string, object> Run(
            string sourceDirectory, string stageDirectory, Dictionary<string, string> expected) {
            return RunWithLoadedAdapter(sourceDirectory, stageDirectory, expected, null);
        }

        public static Dictionary<string, object> RunWithLoadedAdapter(
            string sourceDirectory, string stageDirectory, Dictionary<string, string> expected,
            Action<Type, Dictionary<string, object>> onLoaded) {
            var loaded = new List<Dictionary<string, object>>();
            var missing = new List<string>();
            var errors = new List<Dictionary<string, object>>();
            var constructors = new List<string[]>();
            var methods = new List<Dictionary<string, object>>();
            var services = new List<Dictionary<string, object>>();
            var report = new Dictionary<string, object> {
                {"probe_version", "1.4"}, {"result", "load_failed"},
                {"loaded_scope", "staged_copies_only"},
                {"constructor_invoked", false}, {"transport_validated", false},
                {"constructors", constructors}, {"methods", methods},
                {"services", services}, {"loaded", loaded},
                {"missing", missing}, {"errors", errors}
            };
            var hashes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var registered = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            Action<Assembly, string> note = delegate(Assembly assembly, string path) {
                lock (loaded) {
                string name = assembly.GetName().Name;
                if (!registered.Add(name)) return;
                loaded.Add(new Dictionary<string, object> {
                    {"name", name}, {"version", assembly.GetName().Version.ToString()},
                    {"sha256", Digest(path)}, {"baseline_verified", hashes.ContainsKey(Path.GetFileName(path))}
                });
                }
            };
            ResolveEventHandler resolve = null;
            AssemblyLoadEventHandler onLoad = null;
            bool callbackStarted = false;
            try {
                string source = Path.GetFullPath(sourceDirectory);
                string stage = Path.GetFullPath(stageDirectory);
                if (String.Equals(source.TrimEnd(Path.DirectorySeparatorChar),
                                  stage.TrimEnd(Path.DirectorySeparatorChar), StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException();
                Directory.CreateDirectory(stage);
                if (expected == null || !expected.ContainsKey("SIMNext.P2PSDK.dll"))
                    throw new ArgumentException();
                foreach (var kv in expected) {
                    if (!Regex.IsMatch(kv.Key, @"\A[A-Za-z0-9_.-]+\.dll\z") ||
                        !Regex.IsMatch(kv.Value ?? "", @"\A[0-9a-fA-F]{64}\z"))
                        throw new ArgumentException();
                    hashes.Add(kv.Key, kv.Value.ToLowerInvariant());
                    string original = Path.Combine(source, kv.Key);
                    if (!File.Exists(original)) {
                        missing.Add(Path.GetFileNameWithoutExtension(kv.Key));
                        report["result"] = "required_file_missing";
                        return report;
                    }
                    if (Digest(original) != hashes[kv.Key]) {
                        report["result"] = "hash_mismatch";
                        report["file"] = kv.Key;
                        return report;
                    }
                    string copy = Path.Combine(stage, kv.Key);
                    File.Copy(original, copy, false);
                    if (Digest(copy) != hashes[kv.Key]) throw new IOException();
                }
                onLoad = delegate(object sender, AssemblyLoadEventArgs args) {
                    try {
                        string location = args.LoadedAssembly.Location;
                        if (!String.IsNullOrEmpty(location) && Path.GetFullPath(location).StartsWith(
                            stage.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar,
                            StringComparison.OrdinalIgnoreCase)) note(args.LoadedAssembly, location);
                    } catch { }
                };
                AppDomain.CurrentDomain.AssemblyLoad += onLoad;
                resolve = delegate(object sender, ResolveEventArgs args) {
                    string name = SafeName(args.Name);
                    if (name == "unidentified") return null;
                    string copy = Path.Combine(stage, name + ".dll");
                    if (!File.Exists(copy)) {
                        string original = Path.Combine(source, name + ".dll");
                        if (!File.Exists(original)) {
                            if (!missing.Contains(name)) missing.Add(name);
                            return null;
                        }
                        string before = Digest(original);
                        File.Copy(original, copy, false);
                        if (before != Digest(copy)) throw new IOException();
                    }
                    AssemblyName actual = AssemblyName.GetAssemblyName(copy);
                    if (!String.Equals(actual.FullName, args.Name, StringComparison.OrdinalIgnoreCase)) {
                        if (!missing.Contains(name)) missing.Add(name);
                        throw new FileLoadException("Dependency identity mismatch", args.Name);
                    }
                    Assembly dependency = Assembly.LoadFrom(copy);
                    note(dependency, copy);
                    return dependency;
                };
                AppDomain.CurrentDomain.AssemblyResolve += resolve;
                string targetPath = Path.Combine(stage, "SIMNext.P2PSDK.dll");
                Assembly target = Assembly.LoadFrom(targetPath);
                note(target, targetPath);
                Type adapter = target.GetType("SIMNext.P2PSDK.VVEyeAdapter", true, false);
                foreach (var ctor in adapter.GetConstructors(BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance)) {
                    var names = new List<string>();
                    foreach (var param in ctor.GetParameters()) {
                        names.Add(param.ParameterType.FullName);
                        var operations = new List<Dictionary<string, object>>();
                        foreach (var method in param.ParameterType.GetMethods()) {
                            var args = new List<string>();
                            foreach (var arg in method.GetParameters()) args.Add(arg.ParameterType.FullName);
                            operations.Add(new Dictionary<string, object> {
                                {"name", method.Name}, {"returns", method.ReturnType.FullName},
                                {"parameters", args}
                            });
                        }
                        services.Add(new Dictionary<string, object> {
                            {"type", param.ParameterType.FullName},
                            {"is_interface", param.ParameterType.IsInterface}, {"methods", operations}
                        });
                    }
                    constructors.Add(names.ToArray());
                }
                foreach (var method in adapter.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly)) {
                    if (method.Name != "AddSDKPort" && method.Name != "Cleanup") continue;
                    var args = new List<string>();
                    foreach (var arg in method.GetParameters()) args.Add(arg.ParameterType.FullName);
                    methods.Add(new Dictionary<string, object> {
                        {"name", method.Name}, {"returns", method.ReturnType.FullName}, {"parameters", args}
                    });
                }
                report["assembly_version"] = target.GetName().Version.ToString();
                report["result"] = "load_ok";
                if (onLoaded != null) {
                    lock (loaded) { report["loaded"] = loaded.ToArray(); }
                    callbackStarted = true;
                    onLoaded(adapter, report);
                }
            } catch (Exception error) {
                report["result"] = callbackStarted ? "callback_failed" : "load_failed";
                for (int i = 0; error != null && i < 6; i++, error = error.InnerException) {
                    var item = new Dictionary<string, object> {
                        {"type", error.GetType().FullName}, {"hresult", System.Runtime.InteropServices.Marshal.GetHRForException(error)}
                    };
                    string file = null;
                    var notFound = error as FileNotFoundException;
                    var loadFailure = error as FileLoadException;
                    if (notFound != null) file = notFound.FileName;
                    if (loadFailure != null) file = loadFailure.FileName;
                    if (!String.IsNullOrEmpty(file)) {
                        string name = SafeName(file);
                        if (name != "unidentified") {
                            item["assembly"] = name;
                            if (!missing.Contains(name)) missing.Add(name);
                        }
                    }
                    errors.Add(item);
                }
            } finally {
                lock (loaded) { report["loaded"] = loaded.ToArray(); }
                if (resolve != null) AppDomain.CurrentDomain.AssemblyResolve -= resolve;
                if (onLoad != null) AppDomain.CurrentDomain.AssemblyLoad -= onLoad;
            }
            return report;
        }
    }
}
