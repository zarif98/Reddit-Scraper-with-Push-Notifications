'use client';

import { DEFAULT_COLORS } from '@/types/monitor';

interface ColorPickerProps {
    selectedColor: string;
    onChange: (color: string) => void;
}

export default function ColorPicker({ selectedColor, onChange }: ColorPickerProps) {
    return (
        <div className="color-picker">
            {DEFAULT_COLORS.map((color) => (
                <button
                    key={color}
                    className={`color-option ${selectedColor === color ? 'selected' : ''}`}
                    style={{ backgroundColor: color }}
                    onClick={() => onChange(color)}
                    aria-label={`Select color ${color}`}
                />
            ))}
        </div>
    );
}
