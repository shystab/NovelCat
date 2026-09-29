# Design System

## Direction

NovelCat is a restrained desktop-style writing product. The editor is the visual center; navigation and AI tools sit on quieter secondary surfaces. Glass is reserved for the optional image-background writing mode and must remain readable without blur support.

The author explicitly prefers visible background imagery through the manuscript. Image-background mode defaults to frosted paper with a local clear-paper toggle; reduced-transparency preferences still select solid surfaces. AI history uses a compact anchored popover that follows the sidebar and viewport bounds. Conversation settings use a centered native top-layer dialog with a blurred, dimmed backdrop. Neither replaces the chat or composer. Document selection and confirmations share the modal surface; reduced-transparency preferences replace backdrop blur with dimming.

## Color

- Canvas: cool near-white or cool charcoal depending on theme.
- Surface: white and cool gray layers with clear borders.
- Ink: slate near-black.
- Accent: warm coral-orange, used for primary actions, focus, and active state only.
- Semantic colors: emerald for success, red for destructive actions, amber for warnings.

## Typography

- Product UI: system sans-serif optimized for Chinese and Latin text.
- Manuscript: Novel Serif stack in the editor only.
- UI type uses compact fixed sizes and strong weight contrast; prose remains comfortably spaced.

## Shape

- Controls: 6-8px radius.
- Repeated cards and framed tools: 8-12px radius.
- Pills only for compact status and segmented controls.

## Layout

- Main workspace: chapter navigation, manuscript editor, AI assistant.
- Social pages: persistent page header followed by full-width working surfaces.
- Responsive behavior collapses side-by-side layouts instead of shrinking them beyond usability.

## Interaction

- Most transitions: 150-220ms ease-out.
- Motion communicates hover, focus, selection, loading, or panel state.
- Every interactive element has visible hover, focus, active, and disabled states.
