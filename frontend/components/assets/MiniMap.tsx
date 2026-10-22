"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import mapboxgl from "mapbox-gl";
import { MapPin } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { validCoordinate } from "@/lib/map-data";
import type { Site } from "@/types";

interface MiniMapProps { site?: Site | null; latitude?: number; longitude?: number }

export function MiniMap({ site, latitude, longitude }: MiniMapProps) {
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN?.trim();
  const coordinate = useMemo(() => validCoordinate(latitude, longitude) ?? validCoordinate(site?.latitude, site?.longitude), [latitude, longitude, site]);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markerRef = useRef<mapboxgl.Marker | null>(null);
  const [mapState, setMapState] = useState<"loading" | "ready" | "error">(token && coordinate ? "loading" : "error");

  useEffect(() => {
    if (!token || !coordinate || !mapContainerRef.current) return;
    let loaded = false;
    let disposed = false;
    queueMicrotask(() => { if (!disposed) setMapState("loading"); });
    const fail = () => {
      if (disposed) return;
      window.clearTimeout(timeout);
      mapRef.current?.remove();
      mapRef.current = null;
      setMapState("error");
    };
    const timeout = window.setTimeout(() => { if (!loaded) fail(); }, 12_000);
    try {
      mapboxgl.accessToken = token;
      const map = new mapboxgl.Map({ container: mapContainerRef.current, style: "mapbox://styles/mapbox/dark-v11", center: [coordinate.longitude, coordinate.latitude], zoom: 14, attributionControl: true, interactive: false });
      mapRef.current = map;
      map.once("load", () => {
        if (disposed) return;
        loaded = true;
        window.clearTimeout(timeout);
        const element = document.createElement("span");
        element.className = "block size-4 rounded-full border-2 border-white bg-[#ff5a24] shadow-md";
        markerRef.current = new mapboxgl.Marker({ element }).setLngLat([coordinate.longitude, coordinate.latitude]).addTo(map);
        setMapState("ready");
      });
      map.on("error", () => {
        fail();
      });
    } catch {
      queueMicrotask(fail);
    }
    return () => {
      disposed = true;
      window.clearTimeout(timeout);
      markerRef.current?.remove();
      markerRef.current = null;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  // Coordinate updates are handled below without recreating the map.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, Boolean(coordinate)]);

  useEffect(() => {
    if (!coordinate || mapState !== "ready" || !mapRef.current) return;
    markerRef.current?.setLngLat([coordinate.longitude, coordinate.latitude]);
    mapRef.current.easeTo({ center: [coordinate.longitude, coordinate.latitude], duration: 600 });
  }, [coordinate, mapState]);

  const fallbackReason = !coordinate ? "No valid telemetry or site coordinates are available." : !token ? "Mapbox token was not included in this frontend build." : "Geographic tiles could not be loaded.";
  const ready = Boolean(coordinate && token && mapState === "ready");

  return <GlassCard variant="light" className="flex h-full flex-col justify-between overflow-hidden p-5">
    <div className="mb-3 flex items-center justify-between">
      <div className="flex items-center gap-2"><MapPin className="size-3.5 text-[#ff5a24]" /><h4 className="text-xs font-semibold uppercase tracking-wider">Geospatial Telemetry</h4></div>
      <span className="font-mono text-[10px] text-[#7a7a7a]">{coordinate ? `${coordinate.latitude.toFixed(4)}, ${coordinate.longitude.toFixed(4)}` : "Coordinates unavailable"}</span>
    </div>
    <div className="relative flex h-44 w-full items-center justify-center overflow-hidden rounded-xl border border-black/15 bg-[#111]">
      <div ref={mapContainerRef} className="absolute inset-0" />
      {!ready && <div className="absolute inset-0 grid place-items-center bg-[#eae7df] p-6 text-center text-xs text-black/70">
        <div><MapPin className="mx-auto mb-2 size-5 text-[#ff5a24]" />{coordinate && token && mapState === "loading" ? "Loading geographic map…" : fallbackReason}</div>
      </div>}
    </div>
    <div className="mt-3 flex items-center justify-between text-[11px] text-[#6a6a6a]"><span>Current Site: <strong className="text-black">{site?.name || "Unassigned / depot"}</strong></span><span className={ready ? "text-emerald-600" : "text-amber-700"}>{ready ? "Map ready" : "Stored position"}</span></div>
  </GlassCard>;
}
