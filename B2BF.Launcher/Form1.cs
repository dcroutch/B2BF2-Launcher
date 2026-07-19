using AutoUpdaterDotNET;
using B2BF.Common.Data;
using B2BF.Common.Helpers;
using B2BF.Common.Networking.GameSpy.CdKey;
using B2BF.Common.Networking.GameSpy.Login;
using B2BF.Common.Networking.GameSpy.Report;
using B2BF.Common.Networking.GameSpy.Search;
using B2BF.Common.Networking.Http;
using B2BF.Common.Updater;
using B2BF.Launcher.Helpers;
using Sentry;
using System.Diagnostics;

namespace B2BF.Launcher
{
    public partial class Form1 : Form
    {
        private OldPhoenixUpdater _updater;

        public Form1()
        {
            if (!PlatformHelper.NeedAdmin() && PlatformHelper.IsRunningAsAdmin())
            {

            }

            InitializeComponent();

            _updater = new OldPhoenixUpdater();
            _updater.NotifyAction += OnNotify;
            _updater.ProgressBarAction += OnProgress;
            _updater.StartButtonAction += OnButton;

            LoginServer.Start();
            SearchServer.Start();
            ReportServer.Start();
            HttpServer.Start();
            CdKeyServer.Start();
            ServerListHelper.Start();

            if (Directory.Exists(Path.Combine(Settings.BF2GamePath, "mods")))
            {
                var directories = Directory.GetDirectories(Path.Combine(Settings.BF2GamePath, "mods")).Select(x => x.Replace(Path.Combine(Settings.BF2GamePath, "mods") + "\\", "")).ToArray();
                comboBox2.Items.Clear();
                comboBox2.Items.AddRange(directories);
            }

            checkBox1.Checked = Settings.Fullscreen;
            checkBox2.Checked = Settings.Restart;
            comboBox1.SelectedIndex = comboBox1.Items.IndexOf(Settings.Language);
            comboBox2.SelectedIndex = comboBox2.Items.IndexOf(Settings.Mod);

            Application.ApplicationExit += Application_ApplicationExit;

            AsyncInit();
        }

        private void Application_ApplicationExit(object? sender, EventArgs e)
        {
            Settings.Fullscreen = checkBox1.Checked;
            Settings.Restart = checkBox2.Checked;
            Settings.Language = comboBox1.SelectedItem.ToString();
            Settings.Mod = comboBox2.SelectedItem.ToString();
        }

        private async Task AsyncInit()
        {
            var processes = Process.GetProcessesByName("bf2.exe");
            while (processes.Length > 0)
            {
                if (MessageBox.Show("Battlefield 2 is still running, please close it. Press 'Yes' if you want us to close it for you.", "Battlefield is running", MessageBoxButtons.YesNo) == DialogResult.Yes)
                {
                    foreach (var process in processes)
                    {
                        try
                        {
                            process.Kill();
                        }
                        catch { }
                    }

                    break;
                }

                processes = Process.GetProcessesByName("bf2.exe");
            }

            button1.Enabled = false;

            if (string.IsNullOrEmpty(Settings.GamePath))
            {
                var existingInstall = RegistryHelper.GetBattlefield2Installation();
                var prompt = string.Join("\n\n",
                    "Detected an existing Battlefield 2 installation at:",
                    existingInstall,
                    "Do you want to use that instead of downloading a fresh copy?"
                );
                if (!string.IsNullOrEmpty(existingInstall) &&
                    MessageBox.Show(prompt,
                        "Existing installation detected",
                        MessageBoxButtons.YesNo) ==
                    DialogResult.Yes)
                {
                    Settings.GamePath = existingInstall;
                }
                else
                {
                    Settings.GamePath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Phoenix Games");
                }

                RegistryHelper.WriteBattlefield2Installation();
            }

            Task.Factory.StartNew(() => _updater.Start());
        }

        private void OnButton(bool obj)
        {
            this.Invoke((MethodInvoker)delegate
            {
                if (Directory.Exists(Path.Combine(Settings.BF2GamePath, "mods")))
                {
                    var directories = Directory.GetDirectories(Path.Combine(Settings.BF2GamePath, "mods")).Select(x => x.Replace(Path.Combine(Settings.BF2GamePath, "mods") + "\\", "")).ToArray();
                    comboBox2.Items.Clear();
                    comboBox2.Items.AddRange(directories);
                }
                comboBox2.SelectedIndex = comboBox2.Items.IndexOf(Settings.Mod);

                button1.Enabled = obj;
                button3.Enabled = obj;
            });
        }

        private void OnProgress(double arg1, double arg2)
        {
            progressBar1.Invoke((MethodInvoker)delegate
            {
                progressBar1.Maximum = (int)arg1;
                progressBar1.Value = (int)arg2;
            });
        }

        private void OnNotify(string obj)
        {
            label1.Invoke((MethodInvoker)delegate
            {
                label1.Text = "Status: " + obj;
            });
        }

        private void button1_Click(object sender, EventArgs e)
        {
            _ = ServerListHelper.UpdateServerList();
            RegistryHelper.DisableBF2HubAutoPatching();

            OnNotify("Preflight check...");
            if (!File.Exists(Path.Combine(Settings.BF2GamePath, "dinput8.dll")))
            {
                // download it, TODO
            }

            foreach (var stale in Process.GetProcessesByName("bf2"))
            {
                try { stale.Kill(); stale.WaitForExit(3000); } catch { }
            }

            try
            {
                using var fs = new FileStream(Path.Combine(Settings.BF2GamePath, "BF2.exe"), FileMode.Open);
                fs.Position = 0x5627E0; // position of the bf2hub patch
                fs.WriteByte(0x57); // W
                fs.WriteByte(0x53); // S
                fs.WriteByte(0x32); // 2
                fs.WriteByte(0x5F); // _
                fs.WriteByte(0x33); // 3
                fs.WriteByte(0x32); // 2
                fs.WriteByte(0x2E); // .
                fs.WriteByte(0x64); // d
                fs.WriteByte(0x6C); // l
                fs.WriteByte(0x6C); // l
            }
            catch (IOException ex)
            {
                SentrySdk.CaptureException(ex);
                MessageBox.Show(this,
                    "BF2.exe is still in use by another process (likely a previous game instance that didn't fully exit). Close it and try again.",
                    "Game file in use", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            OnNotify("Launching Game!");

            // Default/vanilla arguments - no +playerName/+playerPassword: BF2's own native
            // "create profile" screen handles identity when no profile exists yet, we don't
            // pre-seed one.
            var arguments = new List<string>
            {
                $"+modPath \"mods/{Settings.Mod}\"",
            };
            if (!Settings.Fullscreen)
            {
                // Default is 1, only add set to 0
                arguments.Add("+fullscreen 0");
            }
            if (Settings.Restart)
            {
                // This is really a boolean flag, so we cannot set it to 0 (game still would not show intro videos)
                arguments.Add("+restart 1");
            }

            arguments.Add($"/language {Settings.Language}");
            // dinput8.dll (Phoenix Network's network hook) refuses to run without this, showing
            // "Please start the game using the B2BF2 Launcher!" - it needs to know where to
            // redirect GameSpy traffic, which is our own loopback servers.
            arguments.Add("/overridehostname 127.0.0.1");

            var psi = new ProcessStartInfo(Path.Combine(Settings.BF2GamePath, "BF2.exe"))
            {
                WorkingDirectory = Settings.BF2GamePath,
                Arguments = string.Join(" ", arguments),
            };
            Process.Start(psi);
        }

        private void checkBox1_CheckedChanged(object sender, EventArgs e)
        {
            Settings.Fullscreen = checkBox1.Checked;
        }

        private void checkBox2_CheckedChanged(object sender, EventArgs e)
        {
            Settings.Restart = checkBox2.Checked;
        }

        private void Form1_FormClosed(object sender, FormClosedEventArgs e)
        {
            Environment.Exit(0);
        }

        private void comboBox1_SelectedIndexChanged(object sender, EventArgs e)
        {
            Settings.Language = comboBox1.SelectedItem.ToString();
        }

        private void comboBox1_SelectedValueChanged(object sender, EventArgs e)
        {
            Settings.Language = comboBox1.SelectedItem.ToString();
        }

        private void comboBox2_SelectedIndexChanged(object sender, EventArgs e)
        {
            Settings.Mod = comboBox2.SelectedItem.ToString();
        }

        private void comboBox2_SelectedValueChanged(object sender, EventArgs e)
        {
            Settings.Mod = comboBox2.SelectedItem.ToString();
        }

        private void Form1_Shown(object sender, EventArgs e)
        {
            AutoUpdater.Mandatory = true;
            AutoUpdater.RunUpdateAsAdmin = PlatformHelper.NeedAdmin();
            AutoUpdater.LetUserSelectRemindLater = false;
            AutoUpdater.TopMost = true;
            //AutoUpdater.ReportErrors = true;
            Task.Factory.StartNew(() => AutoUpdater.Start(Endpoints.LauncherUpdateManifestUrl));
        }

        private void button3_Click(object sender, EventArgs e)
        {
            try
            {
                File.Delete(Path.Combine(Settings.BF2GamePath, "version.txt"));
            }
            catch (Exception ex)
            {

            }

            var result = MessageBox.Show(
                "Yes: Check all files, permanently overwrite any modifications.\nNo: Check only B2BF-specific files, leave all other files untouched.",
                "Validate all game files?",
                MessageBoxButtons.YesNoCancel
            );
            if (result == DialogResult.Cancel)
            {
                return;
            }

            _updater.OverWriteExisting = result == DialogResult.Yes;

            button1.Enabled = false;
            button3.Enabled = false;
            Task.Factory.StartNew(() => _updater.Start());
        }
    }
}
