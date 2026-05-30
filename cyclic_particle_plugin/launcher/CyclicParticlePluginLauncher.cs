using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace CyclicParticlePlugin
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            string exeDir = AppDomain.CurrentDomain.BaseDirectory;
            string scriptPath = Path.Combine(exeDir, "ui", "edit_config.ps1");

            if (!File.Exists(scriptPath))
            {
                MessageBox.Show(
                    "Cannot find the config editor script:\n\n" + scriptPath,
                    "Cyclic Particle PFC Plugin",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return;
            }

            try
            {
                var startInfo = new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = "-STA -NoProfile -ExecutionPolicy Bypass -File \"" + scriptPath + "\"",
                    WorkingDirectory = exeDir,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };

                Process.Start(startInfo);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Failed to start the config editor:\n\n" + ex.Message,
                    "Cyclic Particle PFC Plugin",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }
}
