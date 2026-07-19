namespace B2BF.Common.Data
{
    /// <summary>
    /// Single source of truth for every Phoenix Network / B2BF2 hostname the launcher talks to.
    /// As of 2026-07, b2bf2.net does not resolve at all, so the server list below has no working
    /// backend - there is currently no known replacement. Login no longer goes through Phoenix
    /// Network (see AccountInfo) since the OAuth endpoints this used to depend on were removed
    /// upstream along with b2bf2.net.
    /// </summary>
    public static class Endpoints
    {
        public const string B2bfApiBaseUrl = "https://b2bf2.net";
        public static string ServerListUrl => $"{B2bfApiBaseUrl}/api/gamespy/servers";

        public const string StatsBaseUrl = "https://stats.b2bf2.net";

        public const string CdnBaseUrl = "https://cdn.phoenixnetwork.net";
        public static string GameUpdateManifestUrl => $"{CdnBaseUrl}/updater/game-bf2.json";
        public static string GameUpdateFilesBaseUrl(string gameVersion) => $"{CdnBaseUrl}/updater/versions/client/Battlefield2/{gameVersion}/";
        public static string LauncherUpdateManifestUrl => $"{CdnBaseUrl}/updater/b2bf/client-launcher.xml";

        /// <summary>Port the local HTTP shim (stats proxy) listens on.</summary>
        public const int LocalHttpPort = 8888;
    }
}
