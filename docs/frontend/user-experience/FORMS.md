# Forms & Validation

This guide covers form handling, validation strategies, error display, and accessibility in the AutoMana React frontend.

## Form Library Choice: React Hook Form

**Selected:** React Hook Form + Zod (schema validation)

**Rationale:**
- **Minimal re-renders**: Uncontrolled components; only affected fields update.
- **Small bundle**: ~8.5 kB (vs. Formik ~15 kB).
- **TypeScript support**: Zod provides runtime type checking and excellent IDE hints.
- **Async validation**: Built-in support for field-level async checks (e.g., email uniqueness).
- **Integration**: Works seamlessly with UI libraries (Shadcn, MUI).
- **DX**: Intuitive API; less boilerplate than alternatives.

---

## Validation Strategy

### Schema-Based Validation with Zod

Define validation schemas alongside form components:

```typescript
// src/features/auth/schemas/loginSchema.ts

import { z } from 'zod';

export const loginSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[0-9]/, 'Password must contain at least one digit'),
  rememberMe: z.boolean().optional(),
});

export type LoginFormData = z.infer<typeof loginSchema>;
```

### Client-Side Validation (Real-Time)

```typescript
// src/features/auth/hooks/useLoginForm.ts

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { loginSchema, LoginFormData } from '../schemas/loginSchema';
import { useAuth } from '@/hooks/useAuth';

export const useLoginForm = () => {
  const { login } = useAuth();
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    setError,
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    mode: 'onBlur', // Validate on blur for better UX
  });

  const onSubmit = async (data: LoginFormData) => {
    try {
      await login(data.email, data.password);
    } catch (error: any) {
      // Handle server-side errors (e.g., invalid credentials)
      if (error.response?.status === 401) {
        setError('email', {
          message: 'Invalid email or password',
        });
      } else {
        setError('root', {
          message: error.message || 'Login failed',
        });
      }
    }
  };

  return {
    register,
    handleSubmit: handleSubmit(onSubmit),
    errors,
    isSubmitting,
  };
};
```

### Async Field Validation

Check email uniqueness during signup without waiting for form submission:

```typescript
// src/features/auth/schemas/signupSchema.ts

import { z } from 'zod';
import { apiClient } from '@/utils/api-client';

const emailSchema = z
  .string()
  .email('Invalid email address')
  .refine(
    async (email) => {
      const response = await apiClient.get('/auth/check-email', {
        params: { email },
      });
      return response.data.available; // true if email is available
    },
    { message: 'Email is already in use' }
  );

export const signupSchema = z.object({
  email: emailSchema,
  password: z.string().min(8, 'Password must be at least 8 characters'),
  confirmPassword: z.string(),
}).refine(
  (data) => data.password === data.confirmPassword,
  {
    message: 'Passwords do not match',
    path: ['confirmPassword'], // Set which field the error appears on
  }
);

export type SignupFormData = z.infer<typeof signupSchema>;
```

---

## Common Form Patterns

### Login Form

```typescript
// src/features/auth/components/LoginForm.tsx

import { useLoginForm } from '../hooks/useLoginForm';
import { FormField } from '@/components/forms/FormField';
import { Button } from '@/components/ui/Button';

export function LoginForm() {
  const { register, handleSubmit, errors, isSubmitting } = useLoginForm();

  return (
    <form onSubmit={handleSubmit} className="space-y-4 w-full max-w-md">
      <FormField
        label="Email"
        {...register('email')}
        type="email"
        placeholder="you@example.com"
        error={errors.email?.message}
        disabled={isSubmitting}
      />

      <FormField
        label="Password"
        {...register('password')}
        type="password"
        placeholder="••••••••"
        error={errors.password?.message}
        disabled={isSubmitting}
      />

      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          {...register('rememberMe')}
          disabled={isSubmitting}
        />
        <span className="text-sm text-gray-600">Remember me</span>
      </label>

      {errors.root && (
        <div className="p-3 bg-red-100 border border-red-400 text-red-700 rounded">
          {errors.root.message}
        </div>
      )}

      <Button
        type="submit"
        disabled={isSubmitting}
        className="w-full"
      >
        {isSubmitting ? 'Logging in...' : 'Log In'}
      </Button>
    </form>
  );
}
```

### Search & Filter Form (Stateless)

```typescript
// src/features/cards/components/CardSearch.tsx

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';

interface SearchFilters {
  query: string;
  rarity: string;
  colors: string[];
}

export function CardSearch({ onSearch }: { onSearch: (filters: SearchFilters) => void }) {
  const { register, watch } = useForm<SearchFilters>({
    defaultValues: { query: '', rarity: '', colors: [] },
  });

  // Watch form changes and debounce search
  const filters = watch();

  React.useEffect(() => {
    const timer = setTimeout(() => onSearch(filters), 300);
    return () => clearTimeout(timer);
  }, [filters, onSearch]);

  return (
    <div className="flex gap-4 mb-6">
      <Input
        placeholder="Search cards..."
        {...register('query')}
        className="flex-1"
      />

      <Select {...register('rarity')}>
        <option value="">All Rarities</option>
        <option value="common">Common</option>
        <option value="uncommon">Uncommon</option>
        <option value="rare">Rare</option>
        <option value="mythic">Mythic</option>
      </Select>
    </div>
  );
}
```

### Create/Edit Form with API Integration

```typescript
// src/features/cards/schemas/cardFormSchema.ts

import { z } from 'zod';

export const cardFormSchema = z.object({
  name: z.string().min(1, 'Card name is required'),
  manaCost: z.string().regex(/^\{[^}]*\}/, 'Invalid mana cost format'),
  type: z.string().min(1, 'Card type is required'),
  text: z.string().optional(),
  power: z.string().optional(),
  toughness: z.string().optional(),
  rarity: z.enum(['common', 'uncommon', 'rare', 'mythic']),
});

export type CardFormData = z.infer<typeof cardFormSchema>;
```

```typescript
// src/features/cards/components/CardForm.tsx

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { cardFormSchema, CardFormData } from '../schemas/cardFormSchema';
import { useCreateCard, useUpdateCard } from '../hooks';
import { FormField } from '@/components/forms/FormField';
import { Button } from '@/components/ui/Button';

interface CardFormProps {
  initialData?: CardFormData & { id: string };
  onSuccess?: () => void;
}

export function CardForm({ initialData, onSuccess }: CardFormProps) {
  const createMutation = useCreateCard();
  const updateMutation = useUpdateCard();

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<CardFormData>({
    resolver: zodResolver(cardFormSchema),
    defaultValues: initialData,
  });

  const onSubmit = async (data: CardFormData) => {
    try {
      if (initialData?.id) {
        await updateMutation.mutateAsync({ ...data, id: initialData.id });
      } else {
        await createMutation.mutateAsync(data);
      }
      reset();
      onSuccess?.();
    } catch (error) {
      console.error('Form submission failed:', error);
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <FormField
        label="Card Name"
        {...register('name')}
        error={errors.name?.message}
        disabled={isSubmitting}
      />

      <FormField
        label="Mana Cost"
        {...register('manaCost')}
        placeholder="{2}{U}{R}"
        error={errors.manaCost?.message}
        disabled={isSubmitting}
      />

      <FormField
        label="Card Type"
        {...register('type')}
        placeholder="Creature — Wizard"
        error={errors.type?.message}
        disabled={isSubmitting}
      />

      <FormField
        label="Rules Text"
        {...register('text')}
        as="textarea"
        rows={4}
        error={errors.text?.message}
        disabled={isSubmitting}
      />

      <div className="grid grid-cols-2 gap-4">
        <FormField
          label="Power"
          {...register('power')}
          placeholder="2"
          error={errors.power?.message}
          disabled={isSubmitting}
        />
        <FormField
          label="Toughness"
          {...register('toughness')}
          placeholder="3"
          error={errors.toughness?.message}
          disabled={isSubmitting}
        />
      </div>

      <FormField
        label="Rarity"
        {...register('rarity')}
        as="select"
        error={errors.rarity?.message}
        disabled={isSubmitting}
      >
        <option value="">Select rarity</option>
        <option value="common">Common</option>
        <option value="uncommon">Uncommon</option>
        <option value="rare">Rare</option>
        <option value="mythic">Mythic</option>
      </FormField>

      <Button
        type="submit"
        disabled={isSubmitting}
        className="w-full"
      >
        {isSubmitting ? 'Saving...' : (initialData ? 'Update Card' : 'Create Card')}
      </Button>
    </form>
  );
}
```

### Multi-Step Form (Wizard)

```typescript
// src/features/collection/components/ImportWizard.tsx

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/Button';

const step1Schema = z.object({
  format: z.enum(['csv', 'json', 'manual']),
});

const step2Schema = z.object({
  file: z.instanceof(File).optional(),
  cards: z.array(z.object({
    name: z.string(),
    quantity: z.number().min(1),
  })).optional(),
});

export function ImportWizard() {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({});

  const form = useForm({
    resolver: zodResolver(step === 1 ? step1Schema : step2Schema),
    mode: 'onBlur',
  });

  const onNext = async () => {
    const isValid = await form.trigger();
    if (!isValid) return;

    const data = form.getValues();
    setFormData(prev => ({ ...prev, ...data }));
    setStep(step + 1);
  };

  const onBack = () => setStep(step - 1);

  return (
    <div className="max-w-2xl mx-auto p-6 border rounded-lg">
      <h2 className="text-xl font-bold mb-6">
        Import Collection — Step {step} of 3
      </h2>

      <div className="mb-6">
        {step === 1 && (
          <div className="space-y-4">
            <label>
              <input
                type="radio"
                value="csv"
                {...form.register('format')}
              />
              Upload CSV File
            </label>
            <label>
              <input
                type="radio"
                value="json"
                {...form.register('format')}
              />
              Upload JSON File
            </label>
            <label>
              <input
                type="radio"
                value="manual"
                {...form.register('format')}
              />
              Add Cards Manually
            </label>
          </div>
        )}

        {step === 2 && (
          <div>
            <p className="text-gray-600 mb-4">
              {formData.format === 'csv' && 'Upload your CSV file'}
              {formData.format === 'json' && 'Upload your JSON file'}
              {formData.format === 'manual' && 'Add cards one by one'}
            </p>
            {/* File upload or manual input UI */}
          </div>
        )}
      </div>

      <div className="flex gap-2 justify-between">
        {step > 1 && (
          <Button onClick={onBack} variant="outline">
            Back
          </Button>
        )}
        <div className="ml-auto flex gap-2">
          {step < 3 && (
            <Button onClick={onNext}>
              Next
            </Button>
          )}
          {step === 3 && (
            <Button onClick={() => form.handleSubmit(onSubmit)()}>
              Complete Import
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
```

---

## Error Display

### Field-Level Errors

```typescript
// src/components/forms/FormField.tsx

import { InputHTMLAttributes, TextareaHTMLAttributes, ReactNode } from 'react';

interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  help?: string;
  as?: 'input' | 'textarea' | 'select';
  children?: ReactNode;
}

export function FormField({
  label,
  error,
  help,
  as = 'input',
  className = '',
  ...props
}: FormFieldProps) {
  const baseClass = `w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
    error ? 'border-red-500 focus:ring-red-500' : 'border-gray-300'
  }`;

  const inputComponent = (() => {
    switch (as) {
      case 'textarea':
        return <textarea className={baseClass} {...(props as any)} />;
      case 'select':
        return (
          <select className={baseClass} {...(props as any)}>
            {(props as any).children}
          </select>
        );
      default:
        return <input className={baseClass} {...props} />;
    }
  })();

  return (
    <div className="space-y-1">
      {label && <label className="block text-sm font-medium text-gray-700">{label}</label>}
      {inputComponent}
      {error && <p className="text-sm text-red-600">{error}</p>}
      {help && <p className="text-sm text-gray-500">{help}</p>}
    </div>
  );
}
```

### Form-Level Errors (Root Errors)

```typescript
function MyForm() {
  const { formState: { errors } } = useForm();

  return (
    <form>
      {errors.root && (
        <div className="p-4 mb-6 bg-red-50 border-l-4 border-red-500 rounded">
          <p className="font-semibold text-red-700">
            {typeof errors.root.message === 'string'
              ? errors.root.message
              : 'An error occurred'}
          </p>
        </div>
      )}
      {/* Form fields */}
    </form>
  );
}
```

---

## Submission Flow

### Optimistic Updates + Error Recovery

```typescript
// src/features/cards/hooks/useUpdateCard.ts

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/utils/api-client';
import { CardFormData } from '../schemas/cardFormSchema';

export const useUpdateCard = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CardFormData & { id: string }) => {
      const response = await apiClient.put(`/cards/${data.id}`, data);
      return response.data;
    },
    onMutate: async (data) => {
      // Optimistically update UI
      await queryClient.cancelQueries({ queryKey: ['cards', data.id] });
      const previousData = queryClient.getQueryData(['cards', data.id]);
      queryClient.setQueryData(['cards', data.id], data);
      return { previousData };
    },
    onSuccess: (data) => {
      // Update with server response
      queryClient.setQueryData(['cards', data.id], data);
      queryClient.invalidateQueries({ queryKey: ['cards'] });
    },
    onError: (error, data, context) => {
      // Rollback on error
      if (context?.previousData) {
        queryClient.setQueryData(['cards', data.id], context.previousData);
      }
    },
  });
};
```

---

## Complex Form Scenarios

### Conditional Fields (Show/Hide Based on Input)

```typescript
function CardForm() {
  const { register, watch, formState: { errors } } = useForm<CardFormData>();
  const cardType = watch('type');

  const isBattlefield = cardType?.includes('Creature');
  const isSpell = cardType?.includes('Instant') || cardType?.includes('Sorcery');

  return (
    <form className="space-y-4">
      <FormField
        label="Card Type"
        {...register('type')}
      />

      {isBattlefield && (
        <>
          <FormField label="Power" {...register('power')} />
          <FormField label="Toughness" {...register('toughness')} />
        </>
      )}

      {isSpell && (
        <FormField
          label="Casting Time"
          {...register('castingTime')}
        />
      )}
    </form>
  );
}
```

### Dynamic Field Arrays (Add/Remove Items)

```typescript
// src/features/collection/components/BulkAddCards.tsx

import { useFieldArray, useForm } from 'react-hook-form';
import { Button } from '@/components/ui/Button';
import { FormField } from '@/components/forms/FormField';

interface BulkCardData {
  cards: Array<{ name: string; quantity: number; condition: string }>;
}

export function BulkAddCards() {
  const { register, control, formState: { errors } } = useForm<BulkCardData>({
    defaultValues: { cards: [{}] },
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'cards',
  });

  return (
    <form className="space-y-4">
      {fields.map((field, index) => (
        <div key={field.id} className="flex gap-4 items-start p-4 border rounded">
          <FormField
            label="Card Name"
            placeholder="Black Lotus"
            {...register(`cards.${index}.name`)}
            error={errors.cards?.[index]?.name?.message}
          />

          <FormField
            label="Quantity"
            type="number"
            min="1"
            {...register(`cards.${index}.quantity`, { valueAsNumber: true })}
            error={errors.cards?.[index]?.quantity?.message}
          />

          <FormField
            label="Condition"
            as="select"
            {...register(`cards.${index}.condition`)}
          >
            <option value="near-mint">Near Mint</option>
            <option value="light-play">Light Play</option>
            <option value="moderate">Moderate</option>
            <option value="heavy-play">Heavy Play</option>
          </FormField>

          {fields.length > 1 && (
            <Button
              onClick={() => remove(index)}
              variant="danger"
              type="button"
            >
              Remove
            </Button>
          )}
        </div>
      ))}

      <Button onClick={() => append({})} type="button" variant="outline">
        + Add Card
      </Button>

      <Button type="submit" className="w-full">
        Import Cards
      </Button>
    </form>
  );
}
```

---

## Accessibility

### ARIA Labels and Descriptions

```typescript
function CardForm() {
  const { register, formState: { errors } } = useForm();

  return (
    <form>
      <div className="mb-6">
        <label htmlFor="card-name" className="block text-sm font-medium mb-2">
          Card Name
        </label>
        <input
          id="card-name"
          {...register('name', { required: 'Card name is required' })}
          aria-label="Card Name"
          aria-required="true"
          aria-invalid={!!errors.name}
          aria-describedby={errors.name ? 'card-name-error' : undefined}
        />
        {errors.name && (
          <p id="card-name-error" className="text-red-600 text-sm mt-1" role="alert">
            {errors.name.message}
          </p>
        )}
      </div>
    </form>
  );
}
```

### Focus Management

```typescript
function FormWithFocusManagement() {
  const focusRef = React.useRef<HTMLButtonElement>(null);
  const { handleSubmit } = useForm();

  const onSubmit = async (data: any) => {
    try {
      // Submit form
    } catch (error) {
      // Focus first error field or error message
      focusRef.current?.focus();
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      {/* Fields */}
      <button ref={focusRef} type="submit">
        Submit
      </button>
    </form>
  );
}
```

### Keyboard Navigation

```typescript
function SelectCardRarity({ disabled }: { disabled: boolean }) {
  return (
    <select
      {...register('rarity')}
      disabled={disabled}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.currentTarget.form?.dispatchEvent(
            new Event('submit', { bubbles: true })
          );
        }
      }}
    >
      <option>Select rarity</option>
      <option>Common</option>
      <option>Uncommon</option>
      <option>Rare</option>
      <option>Mythic</option>
    </select>
  );
}
```

---

## Summary

- **Library**: React Hook Form + Zod for minimal re-renders and strong types.
- **Validation**: Schema-based (Zod), client-side real-time, async field checks.
- **Error Display**: Field-level and form-level errors with clear messaging.
- **Patterns**: Login, search, CRUD, multi-step, dynamic arrays.
- **Submission**: Optimistic updates with error recovery.
- **Accessibility**: ARIA attributes, focus management, keyboard navigation.
