import { useEffect, useRef } from "react";
import {
  GeoJSONSource,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  type MapMouseEvent,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { AnalysisArea } from "../api/client";

type Props = {
  centerLat: number;
  centerLon: number;
  area: AnalysisArea | null;
  disabled: boolean;
  onSelect: (lon: number, lat: number) => void;
};

function areaFeature(area: AnalysisArea | null) {
  if (!area) {
    return {
      type: "FeatureCollection" as const,
      features: [],
    };
  }

  const bounds = area.bounds;
  return {
    type: "Feature" as const,
    properties: {},
    geometry: {
      type: "Polygon" as const,
      coordinates: [[
        [bounds.west_deg, bounds.south_deg],
        [bounds.east_deg, bounds.south_deg],
        [bounds.east_deg, bounds.north_deg],
        [bounds.west_deg, bounds.north_deg],
        [bounds.west_deg, bounds.south_deg],
      ]],
    },
  };
}

export default function SetupMap({
  centerLat,
  centerLon,
  area,
  disabled,
  onSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const onSelectRef = useRef(onSelect);
  const disabledRef = useRef(disabled);
  const initialCenterRef = useRef<[number, number]>([centerLon, centerLat]);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    disabledRef.current = disabled;
    const map = mapRef.current;
    if (map) {
      map.getCanvas().style.cursor = disabled ? "not-allowed" : "crosshair";
    }
  }, [disabled]);

  useEffect(() => {
    if (!containerRef.current) return;

    const map = new MapLibreMap({
      container: containerRef.current,
      center: initialCenterRef.current,
      zoom: 14,
      style: {
        version: 8,
        sources: {
          gsi: {
            type: "raster",
            tiles: ["https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "国土地理院",
          },
          "analysis-area": {
            type: "geojson",
            data: {
              type: "FeatureCollection",
              features: [],
            },
          },
        },
        layers: [
          {
            id: "gsi",
            type: "raster",
            source: "gsi",
          },
          {
            id: "analysis-area-fill",
            type: "fill",
            source: "analysis-area",
            paint: {
              "fill-color": "#2563eb",
              "fill-opacity": 0.12,
            },
          },
          {
            id: "analysis-area-outline",
            type: "line",
            source: "analysis-area",
            paint: {
              "line-color": "#1d4ed8",
              "line-width": 3,
            },
          },
        ],
      },
    });

    mapRef.current = map;
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.getCanvas().style.cursor = disabledRef.current ? "not-allowed" : "crosshair";

    markerRef.current = new Marker({ color: "#111827" })
      .setLngLat(initialCenterRef.current)
      .addTo(map);

    const handleClick = (event: MapMouseEvent) => {
      if (disabledRef.current) return;
      onSelectRef.current(event.lngLat.lng, event.lngLat.lat);
    };
    map.on("click", handleClick);

    return () => {
      map.off("click", handleClick);
      markerRef.current?.remove();
      markerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markerRef.current?.setLngLat([centerLon, centerLat]);

    // Viewport movement does not depend on style/source readiness.
    // Do it immediately so geocoder selection can never get stuck waiting for
    // a load event that may already have fired.
    map.stop();
    map.resize();
    if (area) {
      map.fitBounds(
        [
          [area.bounds.west_deg, area.bounds.south_deg],
          [area.bounds.east_deg, area.bounds.north_deg],
        ],
        { padding: 40, maxZoom: 17, duration: 350 },
      );
    } else {
      map.easeTo({ center: [centerLon, centerLat], zoom: 14, duration: 350 });
    }

    const updateAreaSource = () => {
      const source = map.getSource("analysis-area") as GeoJSONSource | undefined;
      source?.setData(areaFeature(area));
    };

    updateAreaSource();
    if (!map.getSource("analysis-area")) {
      map.once("load", updateAreaSource);
      return () => {
        map.off("load", updateAreaSource);
      };
    }
  }, [area, centerLat, centerLon]);

  return (
    <div className="setup-map-wrap">
      <p className="setup-map-help">
        地図をクリックして解析中心を選択できます。四角い枠が解析範囲です。
      </p>
      <div
        ref={containerRef}
        className="setup-map-canvas"
        role="region"
        aria-label="解析場所と範囲を選択する地図"
        aria-disabled={disabled}
      />
      {disabled && <p className="setup-map-disabled">解析中は場所と範囲を変更できません。</p>}
    </div>
  );
}
