using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Windows.Forms;

namespace ScanDesk
{
    internal sealed class DeskForm : Form
    {
        private readonly ComboBox scanners = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 250 };
        private readonly ComboBox resolution = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 250 };
        private readonly Label presetSummary = new Label { Width = 250, Height = 100, ForeColor = Color.FromArgb(75, 94, 107) };
        private int SelectedDpi { get { return resolution.SelectedIndex == 1 ? 9600 : FilmPreset.Dpi; } }
        private readonly ListBox frames = new ListBox { Width = 250, Height = 200, HorizontalScrollbar = true, IntegralHeight = false };
        private readonly Label receipt = new Label { Dock = DockStyle.Fill, Padding = new Padding(24), TextAlign = ContentAlignment.TopLeft, Font = new Font("Segoe UI", 12), ForeColor = Color.FromArgb(75, 94, 107) };
        private readonly Label status = new Label { Dock = DockStyle.Fill, AutoEllipsis = true, TextAlign = ContentAlignment.MiddleLeft };
        private readonly Label details = new Label { Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft, ForeColor = Color.DimGray };
        private readonly List<Control> actions = new List<Control>();
        private readonly string session = Path.Combine(Program.Root, "Scans", DateTime.Now.ToString("yyyy-MM-dd_HHmmss") + "_" + Guid.NewGuid().ToString("N").Substring(0, 6));
        private Twain scanner;
        private bool busy;
        internal string StatusText { get { return status.Text; } }
        public DeskForm()
        {
            Text = "FilmDesk - 35mm film"; Width = 1180; Height = 840; MinimumSize = new Size(1000, 740); StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 10); AutoScaleMode = AutoScaleMode.Dpi; BackColor = Color.FromArgb(243, 246, 248);
            var layout = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 3 };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 300)); layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 96)); layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 52)); Controls.Add(layout);
            var header = new Panel { Dock = DockStyle.Fill, Padding = new Padding(24, 14, 24, 12), BackColor = Color.FromArgb(28, 39, 47) };
            header.Controls.Add(new Label { Dock = DockStyle.Bottom, Height = 26, Text = "A local workspace for your 35mm negatives and slides", ForeColor = Color.FromArgb(193, 209, 215) });
            header.Controls.Add(new Label { Dock = DockStyle.Top, Height = 43, Text = "FilmDesk", ForeColor = Color.White, Font = new Font("Segoe UI", 23, FontStyle.Bold) }); layout.Controls.Add(header, 0, 0); layout.SetColumnSpan(header, 2);
            var sidebar = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, WrapContents = false, AutoScroll = true, Padding = new Padding(20, 12, 16, 12), BackColor = Color.White }; layout.Controls.Add(sidebar, 0, 1);
            Heading(sidebar, "CANON TWAIN SOURCE"); sidebar.Controls.Add(scanners);
            Button(sidebar, "Refresh scanners", RefreshScanners, false, 250);
            Heading(sidebar, "FILM PRESET");
            resolution.Items.Add("4800 dpi (optical)"); resolution.Items.Add("9600 dpi");
            resolution.SelectedIndexChanged += delegate { presetSummary.Text = FilmPreset.Summary(SelectedDpi); };
            resolution.SelectedIndex = 0; sidebar.Controls.Add(resolution); sidebar.Controls.Add(presetSummary);
            Button(sidebar, "Preset settings", ShowPreset, false, 250);
            Button(sidebar, "Open ScanGear for film", StartScan, true, 250);
            Heading(sidebar, "QUIET MODE: ALWAYS PREFERRED");
            sidebar.Controls.Add(new Label { Width = 250, Height = 95, Text = "Before Preview or Scan:\nPreferences > Scanner > Quiet Mode.\n\nThe driver checkbox controls quiet mode; FilmDesk cannot verify it yet.", ForeColor = Color.FromArgb(115, 83, 29) });
            Heading(sidebar, "SCANNED FRAMES"); sidebar.Controls.Add(frames);
            Button(sidebar, "Import / recover images", Import, false, 250);
            Button(sidebar, "Open scan folder", delegate { Directory.CreateDirectory(session); Process.Start(new ProcessStartInfo("explorer.exe", "\"" + session + "\"") { UseShellExecute = true }); }, false, 250);
            var workspace = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(18), RowCount = 3, ColumnCount = 1 };
            workspace.RowStyles.Add(new RowStyle(SizeType.Absolute, 48)); workspace.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); workspace.RowStyles.Add(new RowStyle(SizeType.Absolute, 46)); layout.Controls.Add(workspace, 1, 1);
            var toolbar = new FlowLayoutPanel { Dock = DockStyle.Fill, WrapContents = false, AutoScroll = true };
            Button(toolbar, "Rotate", Rotate, false, 92); Button(toolbar, "Remove", Remove, false, 92);
            workspace.Controls.Add(toolbar, 0, 0);
            var savedFiles = new Panel { Dock = DockStyle.Fill, BackColor = Color.White }; savedFiles.Controls.Add(receipt); workspace.Controls.Add(savedFiles, 0, 1);
            UpdateSavedFile();
            details.Text = "Scans are saved automatically as lossless TIFFs in your scan folder."; workspace.Controls.Add(details, 0, 2);
            var footer = new Panel { Dock = DockStyle.Fill, Padding = new Padding(22, 8, 22, 8), BackColor = Color.White }; footer.Controls.Add(status); layout.Controls.Add(footer, 0, 2); layout.SetColumnSpan(footer, 2);
            frames.SelectedIndexChanged += delegate { try { UpdateSavedFile(); } catch (Exception ex) { Error(ex); } };
            Shown += delegate { RefreshScanners(); };
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (busy) { e.Cancel = true; status.Text = "Close Canon ScanGear, then close FilmDesk."; } };
            FormClosed += delegate { if (scanner != null) scanner.Dispose(); };
        }
        private static void Heading(FlowLayoutPanel panel, string text)
        {
            panel.Controls.Add(new Label { Text = text, Width = 250, Height = 24, ForeColor = Color.FromArgb(91, 108, 119), Font = new Font("Segoe UI", 9, FontStyle.Bold), Margin = new Padding(0, 12, 0, 2) });
        }
        private void Button(FlowLayoutPanel panel, string text, Action action, bool primary, int width)
        {
            var button = new Button { Text = text, Width = width, Height = 37, FlatStyle = FlatStyle.Flat, Cursor = Cursors.Hand, BackColor = primary ? Color.FromArgb(0, 117, 109) : Color.White, ForeColor = primary ? Color.White : Color.FromArgb(39, 57, 70), Margin = new Padding(0, 5, 7, 3) };
            button.FlatAppearance.BorderColor = primary ? button.BackColor : Color.FromArgb(208, 218, 223);
            button.Click += delegate { try { action(); } catch (Exception ex) { Error(ex); } }; actions.Add(button); panel.Controls.Add(button);
        }
        private void SetBusy(bool value, string message)
        {
            busy = value; status.Text = message; scanners.Enabled = frames.Enabled = resolution.Enabled = !value;
            foreach (Control action in actions) action.Enabled = !value;
        }
        private void Error(Exception ex)
        {
            status.Text = ex.Message;
            try { Directory.CreateDirectory(Path.Combine(Program.Root, "Scans")); File.AppendAllText(Path.Combine(Program.Root, "Scans", "errors.log"), DateTime.Now.ToString("s") + " " + ex + Environment.NewLine); } catch (IOException) { }
            MessageBox.Show(this, ex.Message, "FilmDesk", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }
        public void RefreshScanners()
        {
            if (busy) return;
            object previous = scanners.SelectedItem; scanners.Items.Clear();
            using (var twain = new Twain(this))
            {
                // Film scanning uses the real Canon source, never the WIA bridge.
                foreach (TwIdentity item in twain.Discover().Where(s => s.Manufacturer.IndexOf("Canon", StringComparison.OrdinalIgnoreCase) >= 0 && s.Name.IndexOf("WIA", StringComparison.OrdinalIgnoreCase) < 0)) scanners.Items.Add(item);
            }
            if (scanners.Items.Count > 0)
            {
                int found = previous == null ? -1 : scanners.Items.IndexOf(previous); scanners.SelectedIndex = found >= 0 ? found : 0;
                status.Text = "Ready - " + scanners.SelectedItem + ". Check Quiet Mode in ScanGear before scanning.";
            }
            else status.Text = "No Canon TWAIN source found. Check the installed 32-bit Canon ScanGear driver.";
        }
        private void StartScan()
        {
            if (scanners.SelectedItem == null) throw new InvalidOperationException("No Canon TWAIN scanner selected.");
            int dpi = SelectedDpi;
            SetBusy(true, "In ScanGear: set Output Resolution to " + dpi + " dpi, Color(48bit), 100%. Check Quiet Mode and corrections off.");
            try
            {
                scanner = new Twain(this, dpi); scanner.Folder = session;
                scanner.Frame += delegate(Page page) { frames.Items.Add(page); frames.SelectedIndex = frames.Items.Count - 1; status.Text = "Frame " + frames.Items.Count + " saved automatically as TIFF. Close ScanGear when finished."; };
                scanner.Failed += Error;
                scanner.Finished += delegate { scanner = null; SetBusy(false, "ScanGear closed. " + frames.Items.Count + " frames in this session."); };
                scanner.Open((TwIdentity)scanners.SelectedItem); scanner.Enable();
            }
            catch { if (scanner != null) scanner.Dispose(); scanner = null; SetBusy(false, "Scanner could not start."); throw; }
        }
        private Page Selected()
        {
            Page page = frames.SelectedItem as Page;
            if (page == null) throw new InvalidOperationException("Scan or select a film frame first."); return page;
        }
        private void UpdateSavedFile()
        {
            Page page = frames.SelectedItem as Page;
            if (page == null)
            {
                receipt.Text = "Scan and save\n\nLoad the 35mm film holder, then open ScanGear.\nScans save automatically as lossless 48-bit TIFFs.\n\nThe saved filename and location will appear here.\nNo image preview or export step is needed.";
                details.Text = "Scans are saved automatically as lossless TIFFs in your scan folder.";
                return;
            }
            receipt.Text = "Saved file\n\n" + Path.GetFileName(page.Path) + "\n\n" + page.Path + "\n\nUse Open scan folder to access the file.";
            details.Text = "File " + (frames.SelectedIndex + 1) + " / " + frames.Items.Count + "  |  " + page.Width + " x " + page.Height + " px  |  " + Math.Round(page.DpiX) + " DPI  |  " + page.BitsPerPixel + "-bit  |  saved locally";
        }
        private void ShowPreset()
        {
            using (var dialog = new Form { Text = SelectedDpi + " dpi / 48-bit film preset", Width = 650, Height = 820, StartPosition = FormStartPosition.CenterParent, Font = Font, MinimizeBox = false, MaximizeBox = false })
            {
                dialog.Controls.Add(new TextBox { Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill, Text = FilmPreset.Instructions(SelectedDpi), BackColor = Color.White });
                dialog.ShowDialog(this);
            }
        }
        private void Rotate() { Page page = Selected(); page.Rotate(); int index = frames.SelectedIndex; frames.Items[index] = page; frames.SelectedIndex = index; UpdateSavedFile(); }
        private void Remove()
        {
            Selected(); int index = frames.SelectedIndex; frames.Items.RemoveAt(index);
            if (frames.Items.Count > 0) frames.SelectedIndex = Math.Min(index, frames.Items.Count - 1);
            UpdateSavedFile(); status.Text = "Frame removed from this session. Its original file remains in the scan folder.";
        }
        private void Import()
        {
            using (var dialog = new OpenFileDialog { Title = "Recover or import film frames", Filter = "Images|*.png;*.tif;*.tiff;*.jpg;*.jpeg;*.bmp", Multiselect = true, InitialDirectory = Path.Combine(Program.Root, "Scans") })
            {
                if (dialog.ShowDialog(this) != DialogResult.OK) return;
                Directory.CreateDirectory(session);
                foreach (string file in dialog.FileNames)
                {
                    Page imported = Page.Read(file);
                    string extension = Path.GetExtension(file).ToLowerInvariant();
                    bool copyOriginal = extension == ".tif" || extension == ".tiff" || extension == ".jpg" || extension == ".jpeg";
                    string copy = Path.Combine(session, "import-" + Guid.NewGuid().ToString("N") + (copyOriginal ? extension : ".tif"));
                    if (copyOriginal) File.Copy(file, copy); else Export.Image(imported, copy);
                    frames.Items.Add(Page.Read(copy));
                }
                if (frames.Items.Count > 0) frames.SelectedIndex = frames.Items.Count - 1;
            }
        }
    }
}
