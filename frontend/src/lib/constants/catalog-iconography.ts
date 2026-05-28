/**
 * Curated subset of Fluent UI icon names and color palette for the catalog
 * Vertical entity. Closed lists keep the sidebar from breaking on bad input.
 *
 * `label` is shown to the user (español); `key` is the Fluent UI icon
 * identifier (inglés, stable). Add to `VERTICAL_ICON_COMPONENTS` in the
 * `IconPicker` component to expose new keys.
 */

export const VERTICAL_ICON_OPTIONS = [
  { key: "Sparkle24Regular", label: "Brillo" },
  { key: "Heart24Regular", label: "Corazón" },
  { key: "HeartPulse24Regular", label: "Pulso" },
  { key: "Stethoscope24Regular", label: "Estetoscopio" },
  { key: "Tooth24Regular", label: "Diente" },
  { key: "Eye24Regular", label: "Ojo" },
  { key: "Brain24Regular", label: "Cerebro" },
  { key: "Leaf24Regular", label: "Hoja" },
  { key: "Beaker24Regular", label: "Vaso" },
  { key: "Pill24Regular", label: "Pastilla" },
  { key: "Syringe24Regular", label: "Jeringa" },
  { key: "Bandage24Regular", label: "Vendaje" },
  { key: "Person24Regular", label: "Persona" },
  { key: "PersonHeart24Regular", label: "Cuidado" },
  { key: "Baby24Regular", label: "Bebé" },
  { key: "Drop24Regular", label: "Gota" },
  { key: "Star24Regular", label: "Estrella" },
  { key: "Crown24Regular", label: "Premium" },
  { key: "Wand24Regular", label: "Varita" },
  { key: "Flash24Regular", label: "Rayo" },
] as const;

export type VerticalIconKey = (typeof VERTICAL_ICON_OPTIONS)[number]["key"];

/**
 * Curated palette for Vertical.color picker. Light/dark friendly.
 * Free hex input is still allowed via the manual field in `ColorPicker`.
 */
export const VERTICAL_COLOR_PALETTE = [
  "#EF4444", // red
  "#F59E0B", // amber
  "#22C55E", // green
  "#06B6D4", // cyan
  "#3B82F6", // blue
  "#8B5CF6", // violet
  "#EC4899", // pink
  "#FF6B6B", // coral
  "#10B981", // emerald
  "#F97316", // orange
  "#6366F1", // indigo
  "#6B7280", // gray
] as const;
