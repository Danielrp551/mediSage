"use client";

import { Field, type FieldProps } from "@fluentui/react-components";
import type { ReactElement } from "react";

export interface FormFieldProps extends Omit<FieldProps, "validationState" | "validationMessage"> {
  error?: string;
  children: ReactElement;
}

export function FormField({ error, children, ...rest }: FormFieldProps) {
  return (
    <Field {...rest} validationState={error ? "error" : undefined} validationMessage={error}>
      {children}
    </Field>
  );
}
