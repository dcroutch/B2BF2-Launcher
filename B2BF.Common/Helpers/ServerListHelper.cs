using B2BF.Common.Data;
using B2BF.Common.Models;
using Newtonsoft.Json;
using Sentry;
using System.Timers;

namespace B2BF.Common.Helpers
{
    public static class ServerListHelper
    {
        public static List<GameSpyServer> Servers { get; private set; } = new();

        private static System.Timers.Timer _timer = new System.Timers.Timer(30000);
        private static HttpClient _httpClient = new HttpClient();

        static ServerListHelper() 
        {
            _timer.Elapsed += _timer_Elapsed;
            _timer.AutoReset = true;
            _timer.Start();
        }

        public static void Start()
        {

        }

        public static async Task UpdateServerList()
        {
            try
            {
                var str = await _httpClient.GetStringAsync(Endpoints.ServerListUrl);
                var serverList = JsonConvert.DeserializeObject<List<GameSpyServer>>(str);

                Servers = serverList ?? new List<GameSpyServer>();
            }
            catch (Exception ex)
            {
                SentrySdk.CaptureException(ex);
            }
        }

        private static async void _timer_Elapsed(object? sender, ElapsedEventArgs e)
        {
            await UpdateServerList();
        }
    }
}