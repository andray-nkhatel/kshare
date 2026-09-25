using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;

namespace KShare;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new ViewerForm());
    }
}

internal sealed class ViewerForm : Form
{
    private readonly ComboBox _hosts = new() { DropDownStyle = ComboBoxStyle.DropDown, Width = 280 };
    private readonly TextBox _pin = new() { Width = 80, MaxLength = 6, PlaceholderText = "PIN" };
    private readonly Button _connect = new() { Text = "Watch", AutoSize = true };
    private readonly PictureBox _screen = new() { Dock = DockStyle.Fill, SizeMode = PictureBoxSizeMode.Zoom, BackColor = Color.Black };
    private readonly Label _status = new() { AutoSize = true, Padding = new Padding(8, 6, 8, 6) };
    private CancellationTokenSource? _watch;
    private readonly Discovery _discovery = new();

    public ViewerForm()
    {
        Text = "KShare";
        Width = 1100;
        Height = 700;
        MinimumSize = new Size(640, 400);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 10f);

        var bar = new FlowLayoutPanel
        {
            Dock = DockStyle.Top,
            AutoSize = true,
            Padding = new Padding(8),
            WrapContents = false,
        };
        bar.Controls.Add(new Label { Text = "Host", AutoSize = true, Padding = new Padding(0, 6, 6, 0) });
        bar.Controls.Add(_hosts);
        bar.Controls.Add(_pin);
        bar.Controls.Add(_connect);
        bar.Controls.Add(_status);
        Controls.Add(_screen);
        Controls.Add(bar);

        _connect.Click += async (_, _) => await ToggleWatch();
        FormClosing += (_, _) => _watch?.Cancel();
        Shown += async (_, _) => await RefreshHosts();
    }

    private async Task RefreshHosts()
    {
        _status.Text = "Looking for hosts…";
        var found = await _discovery.Listen(TimeSpan.FromSeconds(2));
        _hosts.Items.Clear();
        foreach (var host in found)
            _hosts.Items.Add(host);
        if (_hosts.Items.Count > 0)
        {
            _hosts.SelectedIndex = 0;
            _status.Text = "Enter the PIN from Omarchy.";
        }
        else
        {
            _status.Text = "No host yet. Type http://address:47330/ or start sharing on Omarchy.";
        }
    }

    private async Task ToggleWatch()
    {
        if (_watch is not null)
        {
            _watch.Cancel();
            return;
        }

        var raw = (_hosts.Text ?? "").Trim();
        if (raw.Length == 0)
        {
            _status.Text = "Enter a host URL.";
            return;
        }
        if (!raw.Contains("://", StringComparison.Ordinal))
            raw = "http://" + raw;
        if (!Uri.TryCreate(raw, UriKind.Absolute, out var uri))
        {
            _status.Text = "That host address is not valid.";
            return;
        }

        _watch = new CancellationTokenSource();
        _connect.Text = "Stop";
        _status.Text = "Connecting…";
        try
        {
            await Watch(uri, _pin.Text.Trim(), _watch.Token);
            _status.Text = "Stopped.";
        }
        catch (OperationCanceledException)
        {
            _status.Text = "Stopped.";
        }
        catch (Exception ex)
        {
            _status.Text = ex.Message;
        }
        finally
        {
            _watch.Dispose();
            _watch = null;
            _connect.Text = "Watch";
        }
    }

    private async Task Watch(Uri host, string pin, CancellationToken cancel)
    {
        using var handler = new HttpClientHandler { UseCookies = true, CookieContainer = new CookieContainer() };
        using var http = new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan };
        var baseUri = new Uri(host.GetLeftPart(UriPartial.Authority));
        var pair = await http.PostAsync(
            new Uri(baseUri, "/api/pair"),
            new StringContent("{\"pin\":" + JsonSerializer.Serialize(pin) + "}", Encoding.UTF8, "application/json"),
            cancel);
        if (pair.StatusCode == HttpStatusCode.Forbidden)
            throw new InvalidOperationException("Wrong PIN.");
        pair.EnsureSuccessStatusCode();

        using var response = await http.GetAsync(new Uri(baseUri, "/stream"), HttpCompletionOption.ResponseHeadersRead, cancel);
        if (response.StatusCode == HttpStatusCode.Unauthorized)
            throw new InvalidOperationException("The host rejected the session.");
        response.EnsureSuccessStatusCode();
        _status.Text = "Live";

        await using var body = await response.Content.ReadAsStreamAsync(cancel);
        var buffer = new byte[64 * 1024];
        var pending = new MemoryStream();
        while (!cancel.IsCancellationRequested)
        {
            var read = await body.ReadAsync(buffer, cancel);
            if (read == 0)
                break;
            pending.Write(buffer, 0, read);
            DrainFrames(pending);
        }
    }

    private void DrainFrames(MemoryStream pending)
    {
        var data = pending.GetBuffer();
        var length = (int)pending.Length;
        var start = IndexOf(data, length, 0, new byte[] { 0xFF, 0xD8 });
        while (start >= 0)
        {
            var end = IndexOf(data, length, start + 2, new byte[] { 0xFF, 0xD9 });
            if (end < 0)
                break;
            var count = end + 2 - start;
            var copy = new byte[count];
            Buffer.BlockCopy(data, start, copy, 0, count);
            ShowFrame(copy);
            var rest = length - (end + 2);
            if (rest > 0)
                Buffer.BlockCopy(data, end + 2, data, 0, rest);
            pending.SetLength(rest);
            pending.Position = rest;
            data = pending.GetBuffer();
            length = rest;
            start = IndexOf(data, length, 0, new byte[] { 0xFF, 0xD8 });
        }
    }

    private void ShowFrame(byte[] jpeg)
    {
        void Apply()
        {
            using var incoming = new MemoryStream(jpeg, writable: false);
            using var image = Image.FromStream(incoming);
            var previous = _screen.Image;
            _screen.Image = new Bitmap(image);
            previous?.Dispose();
        }

        if (InvokeRequired)
            BeginInvoke(Apply);
        else
            Apply();
    }

    private static int IndexOf(byte[] data, int length, int from, byte[] pattern)
    {
        for (var i = from; i <= length - pattern.Length; i++)
        {
            var match = true;
            for (var j = 0; j < pattern.Length; j++)
            {
                if (data[i + j] != pattern[j])
                {
                    match = false;
                    break;
                }
            }
            if (match)
                return i;
        }
        return -1;
    }
}

internal sealed class Discovery
{
    public async Task<IReadOnlyList<string>> Listen(TimeSpan duration)
    {
        var found = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
        using var udp = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);
        udp.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
        udp.Bind(new IPEndPoint(IPAddress.Any, 47331));
        udp.ReceiveTimeout = 400;
        var buffer = new byte[2048];
        var deadline = DateTime.UtcNow + duration;
        while (DateTime.UtcNow < deadline)
        {
            try
            {
                var result = await udp.ReceiveFromAsync(buffer, SocketFlags.None, new IPEndPoint(IPAddress.Any, 0));
                var json = Encoding.UTF8.GetString(buffer, 0, result.ReceivedBytes);
                using var doc = JsonDocument.Parse(json);
                if (doc.RootElement.TryGetProperty("magic", out var magic) && magic.GetString() != "kshare-announce-v1")
                    continue;
                if (!doc.RootElement.TryGetProperty("port", out var port))
                    continue;
                var remote = (IPEndPoint)result.RemoteEndPoint;
                found.Add($"http://{remote.Address}:{port.GetInt32()}/");
            }
            catch (SocketException)
            {
            }
            catch (JsonException)
            {
            }
        }
        return found.ToList();
    }
}
