def build_audio_filter(selected: list[tuple[int, float]]) -> str:
    if not selected:
        raise ValueError("Please select at least one audio track.")

    filters = []
    maps = []

    for i, (stream_index, volume) in enumerate(selected):
        volume_text = f"{volume:.3f}"
        filters.append(f"[0:{stream_index}]volume={volume_text}[a{i}]")
        maps.append(f"[a{i}]")

    amix_inputs = len(maps)

    amix = (
        f"{''.join(maps)}"
        f"amix=inputs={amix_inputs}:duration=longest:"
        f"dropout_transition=0:normalize=0[aout]"
    )

    return ";".join(filters + [amix])
