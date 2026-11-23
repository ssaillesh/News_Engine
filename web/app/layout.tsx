import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono } from "next/font/google";
import { Shell } from "@/components/Shell";
import "./globals.css";

const archivo = Archivo({ variable: "--font-archivo", subsets: ["latin"], weight: ["400", "500", "600", "700"] });
const plexMono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500", "600"] });

export const metadata: Metadata = {
  title: { default: "Investment Hub", template: "%s · Investment Hub" },
  description: "Policy to markets: Washington, news impact, prices and your portfolio in one terminal.",
};

// Applied before first paint so a light-theme choice never flashes dark.
const THEME_SCRIPT = `try{var t=localStorage.getItem("hub:theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-theme="dark" className={`${archivo.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        {/* Server config, known at build time: show "Logout" only when the gate is on. */}
        <Shell signOut={Boolean(process.env.SITE_PASSWORD)}>{children}</Shell>
      </body>
    </html>
  );
}
