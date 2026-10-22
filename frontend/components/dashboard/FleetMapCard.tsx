"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import mapboxgl from "mapbox-gl";
import { Navigation } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import { STATUS_CONFIG } from "@/lib/constants";
import { coordinateExtent, equipmentCoordinate, equipmentSites, validCoordinate } from "@/lib/map-data";
import type { EquipmentListItem, EquipmentStatus } from "@/types";
import { cn } from "@/lib/utils";

interface FleetMapCardProps { equipmentList: EquipmentListItem[] }
type MarkerItem = { marker: mapboxgl.Marker; popup: mapboxgl.Popup; element: HTMLElement };

function statusFor(asset: EquipmentListItem): EquipmentStatus {
  return asset.status in STATUS_CONFIG ? asset.status as EquipmentStatus : "UNASSIGNED";
}

function appendText(parent: HTMLElement, text: string, className?: string) {
  const element = document.createElement("div");
  if (className) element.className = className;
  element.textContent = text;
  parent.appendChild(element);
}

function markerElement(asset: EquipmentListItem, color: string) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = "relative flex cursor-pointer items-center justify-center";
  element.setAttribute("aria-label", `Open ${asset.id}`);
  const pulse = document.createElement("span");
  pulse.className = "absolute size-[22px] animate-ping rounded-full opacity-25";
  pulse.style.backgroundColor = color;
  const dot = document.createElement("span");
  dot.className = "size-3 rounded-full border-2 border-white shadow-md";
  dot.style.backgroundColor = color;
  const label = document.createElement("span");
  label.className = "absolute top-4 whitespace-nowrap rounded border border-white/20 bg-black px-1 text-[8px] font-bold text-white";
  label.textContent = asset.id;
  element.append(pulse, dot, label);
  return element;
}

function popupContent(asset: EquipmentListItem, coordinate: { latitude: number; longitude: number }, status: EquipmentStatus) {
  const root = document.createElement("div");
  root.className = "min-w-36 text-xs leading-5 text-white";
  appendText(root, `${asset.id} · ${asset.type}`, "font-bold text-[#ff5a24]");
  appendText(root, `Status: ${STATUS_CONFIG[status].label}`);
  appendText(root, `Site: ${asset.site?.name || "Depot / unassigned"}`);
  appendText(root, `GPS: ${coordinate.latitude.toFixed(4)}, ${coordinate.longitude.toFixed(4)}`, "font-mono text-white/70");
  return root;
}

export function FleetMapCard({ equipmentList }: FleetMapCardProps) {
  const router = useRouter();
  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN?.trim();
  const [selectedSiteId, setSelectedSiteId] = useState("ALL");
  const [mapState, setMapState] = useState<"loading" | "ready" | "error">(token ? "loading" : "error");
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<Map<string, MarkerItem>>(new Map());
  const lastBoundsKey = useRef("");
  const sites = useMemo(() => equipmentSites(equipmentList), [equipmentList]);
  const filteredAssets = useMemo(() => selectedSiteId === "ALL" ? equipmentList : equipmentList.filter(asset => asset.site?.id === selectedSiteId), [equipmentList, selectedSiteId]);
  const locatedAssets = useMemo(() => filteredAssets.flatMap(asset => {
    const coordinate = equipmentCoordinate(asset);
    return coordinate ? [{ asset, coordinate }] : [];
  }), [filteredAssets]);

  const fitAssets = (assets = locatedAssets) => {
    const map = mapRef.current;
    if (!map || !assets.length) return;
    const bounds = new mapboxgl.LngLatBounds();
    assets.forEach(({ coordinate }) => bounds.extend([coordinate.longitude, coordinate.latitude]));
    map.fitBounds(bounds, { padding: 55, maxZoom: 14, duration: 700 });
  };

  useEffect(() => {
    if (!token || !mapContainerRef.current) return;
    const markers = markersRef.current;
    let loaded = false;
    let disposed = false;
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
      const map = new mapboxgl.Map({ container: mapContainerRef.current, style: "mapbox://styles/mapbox/dark-v11", center: [78.5, 20.5], zoom: 4, attributionControl: true });
      mapRef.current = map;
      map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
      map.once("load", () => { if (disposed) return; loaded = true; window.clearTimeout(timeout); map.resize(); setMapState("ready"); });
      map.on("error", () => {
        fail();
      });
    } catch {
      queueMicrotask(fail);
    }
    return () => {
      disposed = true;
      window.clearTimeout(timeout);
      markers.forEach(item => { item.popup.remove(); item.marker.remove(); });
      markers.clear();
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, [token]);

  useEffect(() => {
    if (mapState !== "ready" || !mapRef.current) return;
    const visibleIds = new Set(locatedAssets.map(({ asset }) => asset.id));
    for (const [id, item] of markersRef.current) {
      if (!visibleIds.has(id)) { item.popup.remove(); item.marker.remove(); markersRef.current.delete(id); }
    }
    for (const { asset, coordinate } of locatedAssets) {
      const status = statusFor(asset);
      const old = markersRef.current.get(asset.id);
      if (old) {
        old.marker.setLngLat([coordinate.longitude, coordinate.latitude]);
        old.popup.setDOMContent(popupContent(asset, coordinate, status));
        (old.element.children[0] as HTMLElement).style.backgroundColor = STATUS_CONFIG[status].color;
        (old.element.children[1] as HTMLElement).style.backgroundColor = STATUS_CONFIG[status].color;
        continue;
      }
      const element = markerElement(asset, STATUS_CONFIG[status].color);
      element.addEventListener("click", () => router.push(`/assets/${encodeURIComponent(asset.id)}`));
      const popup = new mapboxgl.Popup({ offset: 16, closeButton: false, focusAfterOpen: false }).setDOMContent(popupContent(asset, coordinate, status));
      const marker = new mapboxgl.Marker({ element }).setLngLat([coordinate.longitude, coordinate.latitude]).setPopup(popup).addTo(mapRef.current);
      element.addEventListener("mouseenter", () => popup.setLngLat(marker.getLngLat()).addTo(mapRef.current!));
      element.addEventListener("mouseleave", () => popup.remove());
      element.addEventListener("focus", () => popup.setLngLat(marker.getLngLat()).addTo(mapRef.current!));
      element.addEventListener("blur", () => popup.remove());
      markersRef.current.set(asset.id, { marker, popup, element });
    }
    const boundsKey = selectedSiteId + ":" + [...visibleIds].join(",");
    if (lastBoundsKey.current !== boundsKey) {
      fitAssets();
      lastBoundsKey.current = boundsKey;
    }
  // fitAssets is derived from locatedAssets and intentionally not a dependency.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locatedAssets, selectedSiteId, mapState, router]);

  const handleSiteSelect = (siteId: string) => {
    setSelectedSiteId(siteId);
    if (siteId === "ALL") return;
    const site = sites.find(item => item.id === siteId);
    const coordinate = site && validCoordinate(site.latitude, site.longitude);
    if (coordinate && mapRef.current) mapRef.current.flyTo({ center: [coordinate.longitude, coordinate.latitude], zoom: 13, essential: true });
  };

  const extent = coordinateExtent(locatedAssets.map(item => item.coordinate));
  const project = (latitude: number, longitude: number) => ({
    left: `${extent && extent.maxLongitude !== extent.minLongitude ? 8 + (longitude - extent.minLongitude) / (extent.maxLongitude - extent.minLongitude) * 84 : 50}%`,
    top: `${extent && extent.maxLatitude !== extent.minLatitude ? 8 + (extent.maxLatitude - latitude) / (extent.maxLatitude - extent.minLatitude) * 84 : 50}%`,
  });
  const fallback = !token || mapState === "error";

  return <GlassCard variant="light" className="relative flex flex-col justify-between overflow-hidden p-7">
    <div className="z-10 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
      <div>
        <div className="flex items-center gap-2">
          <span className="size-2 bg-[#ff5a24]" />
          <h3 className="text-xs font-semibold uppercase tracking-wider">Tactical Fleet Map</h3>
          <span className={cn("rounded-full border px-2 py-0.5 font-mono text-[10px]", mapState === "ready" ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700" : "border-amber-500/20 bg-amber-500/10 text-amber-700")}>
            {mapState === "ready" ? "Geographic map ready" : fallback ? "Geographic map unavailable" : "Loading geographic map"}
          </span>
        </div>
        <p className="mt-1 text-xs text-[#6a6a6a]">Latest stored GPS positions; stream state is shown in the top bar.</p>
      </div>
      <div className="flex max-w-full items-center gap-1.5 overflow-x-auto rounded-xl border border-black/10 bg-white/70 p-1 text-xs">
        <button onClick={() => handleSiteSelect("ALL")} className={cn("whitespace-nowrap rounded-lg px-3 py-1 font-medium", selectedSiteId === "ALL" ? "bg-[#111] text-white" : "text-[#555]")}>All Sites ({equipmentList.length})</button>
        {sites.map(site => <button key={site.id} onClick={() => handleSiteSelect(site.id)} className={cn("whitespace-nowrap rounded-lg px-3 py-1 font-medium", selectedSiteId === site.id ? "bg-[#111] text-white" : "text-[#555]")}>{site.name}</button>)}
      </div>
    </div>
    <div className="relative my-6 h-80 w-full overflow-hidden rounded-2xl border border-black/15 bg-[#111] sm:h-96">
      <div ref={mapContainerRef} className="absolute inset-0" />
      {fallback && <div className="absolute inset-0 overflow-hidden bg-[#eae7df]">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(0,0,0,.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(0,0,0,.05)_1px,transparent_1px)] bg-[size:2rem_2rem]" />
        {locatedAssets.map(({ asset, coordinate }) => <Link key={asset.id} href={`/assets/${encodeURIComponent(asset.id)}`} style={project(coordinate.latitude, coordinate.longitude)} className="group absolute z-20 -translate-x-1/2 -translate-y-1/2">
          <span className="block size-5 rounded-full border-2 border-white shadow" style={{ backgroundColor: STATUS_CONFIG[statusFor(asset)].color }} />
          <span className="absolute bottom-6 left-1/2 hidden -translate-x-1/2 whitespace-nowrap rounded bg-black px-2 py-1 text-[10px] text-white group-hover:block">{asset.id} · {asset.site?.name || "Unassigned"}<br />{coordinate.latitude.toFixed(4)}, {coordinate.longitude.toFixed(4)}</span>
        </Link>)}
        <div className="absolute inset-x-6 top-5 rounded-lg bg-white/90 p-3 text-center text-xs text-black shadow">
          {token ? "The geographic tiles could not be loaded. Check token permissions, URL restrictions, WebGL, and browser network errors." : "Mapbox token was not included in this frontend build. Showing relative stored positions without geographic tiles."}
        </div>
      </div>}
      <button onClick={() => { setSelectedSiteId("ALL"); fitAssets(locatedAssets); }} className="absolute bottom-4 right-4 z-30 flex items-center gap-1.5 rounded-lg bg-white/90 px-3 py-1.5 text-xs font-medium shadow"><Navigation className="size-3 text-[#ff5a24]" />Center Fleet</button>
      {locatedAssets.length === 0 && <div className="absolute inset-0 z-20 grid place-items-center text-sm text-white/80">No valid equipment coordinates for this filter.</div>}
    </div>
    {locatedAssets.length < filteredAssets.length && <p className="text-xs text-amber-700">{filteredAssets.length - locatedAssets.length} asset(s) omitted because neither telemetry nor site coordinates are valid.</p>}
  </GlassCard>;
}
