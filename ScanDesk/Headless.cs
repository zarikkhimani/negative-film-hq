using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows.Forms;

namespace ScanDesk
{
    internal static class Headless
    {
        internal static int Run(string[] args)
        {
            bool acquire = args[0] == "--headless-scan";
            string reports = Path.Combine(Program.Root, "test-output"); Directory.CreateDirectory(reports);
            string report = Path.Combine(reports, acquire ? "headless-scan.txt" : "headless-probe.txt");
            var log = new StringBuilder();
            Action<string> write = delegate(string line) { log.AppendLine(DateTime.Now.ToString("s") + " " + line); File.WriteAllText(report, log.ToString()); };
            int exitCode = 1, received = 0;
            bool failed = false;
            try
            {
                if (acquire && !args.Contains("--quiet-verified")) throw new InvalidOperationException("Inspect Canon's Quiet Mode and preservation settings before this experimental hardware test, then pass --quiet-verified. This flag is an operator attestation, not automatic verification.");
                using (var form = new Form { Text = "FilmDesk - hidden-window scan test", Width = 760, Height = 340, StartPosition = FormStartPosition.CenterScreen })
                using (var twain = new Twain(form, 4800))
                {
                    var status = new Label { Dock = DockStyle.Fill, Padding = new Padding(20), Font = new Font("Segoe UI", 11), Text = "Preparing a 4800 dpi / 48-bit film test.\nNo preview or image display.\n\nCanon's Quiet Mode must have been checked before this test." };
                    form.Controls.Add(status);
                    twain.Folder = Path.Combine(Program.Root, "Scans", DateTime.Now.ToString("yyyy-MM-dd_HHmmss") + "_hidden_" + Guid.NewGuid().ToString("N").Substring(0, 6));
                    twain.Diagnostic += write;
                    twain.Frame += delegate(Page page) { received++; write("SAVED: " + page.Path + " | " + page.Width + " x " + page.Height + " | " + page.DpiX + " x " + page.DpiY + " dpi | " + page.BitsPerPixel + " bits"); };
                    twain.Failed += delegate(Exception ex) { failed = true; write("FAIL: " + ex); exitCode = 1; };
                    twain.Finished += delegate { if (!failed && received == 1) { exitCode = 0; write("PASS: one scan saved without the Canon setup window or a preview."); } else { exitCode = 1; write("The test did not complete successfully. Saved frames: " + received); } form.BeginInvoke((Action)delegate { form.Close(); }); };
                    form.FormClosed += delegate { twain.Dispose(); };
                    form.Shown += delegate
                    {
                        try
                        {
                            var sources = twain.Discover();
                            var canon = sources.Single(s => s.Name == "Canon MG8100 ser");
                            twain.Open(canon); write("Connected to " + canon.Name);
                            if (acquire) write("Quiet Mode manually checked in the driver UI before the test; persistence during hidden scanning cannot be read through TWAIN.");
                            // Platen coordinates within Canon's reported default film frame:
                            // (3.42334, 1.29666) - (4.37000, 2.71666) inches.
                            twain.PrepareHidden(TwFrame.Inches(3.45, 1.35, 4.35, 1.60));
                            if (!acquire) { exitCode = 0; write("PASS: coordinate request/readback completed. No scan or preview requested."); form.Close(); return; }
                            status.Text = "Requesting a 0.90 x 0.25 inch film scan at 4800 dpi.\nWaiting for Canon to return image data.\n48-bit TIFF will save automatically if the driver delivers it.\n\nCanon's setup window is disabled.\nNo preview was requested.";
                            twain.EnableHidden();
                        }
                        catch (Exception ex) { write("FAIL: " + ex); exitCode = 1; form.Close(); }
                    };
                    Application.Run(form);
                }
            }
            catch (Exception ex) { write("FAIL: " + ex); }
            return exitCode;
        }
    }
}
