import {
  documentTypeSchema,
  extensionOf,
  uploadDocumentSchema,
  validateFile,
} from '@/features/documents/schemas/document.schemas';

describe('document validation', () => {
  it('accepts supported extensions case-insensitively', () => {
    expect(extensionOf('Passport.PDF')).toBe('.pdf');
    expect(validateFile(new File(['content'], 'photo.JPEG', { type: 'image/jpeg' }))).toBeNull();
  });

  it('rejects empty, oversized, and executable files', () => {
    expect(validateFile(new File([], 'empty.pdf'))?.message).toMatch(/empty/);
    expect(validateFile(new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.pdf'))?.message).toMatch(
      /limit/,
    );
    expect(validateFile(new File(['x'], 'malware.exe'))?.message).toMatch(/not an accepted type/);
  });

  it('requires valid classification and owner metadata', () => {
    expect(() =>
      uploadDocumentSchema.parse({
        name: 'x',
        category_id: '',
        document_type_id: '',
        owner_type: 'employee',
        owner_id: '',
      }),
    ).toThrow();
  });

  it('normalises a type extension narrowing and refuses widening it', () => {
    const base = {
      name: 'Passport',
      code: 'PASS',
      description: '',
      status: 'active',
      category_id: '11111111-1111-4111-8111-111111111111',
      requires_expiry: true,
      is_sensitive: true,
    };
    expect(documentTypeSchema.parse({ ...base, allowed_extensions: 'PDF, .jpg' }).allowed_extensions).toBe(
      '.jpg,.pdf',
    );
    expect(() => documentTypeSchema.parse({ ...base, allowed_extensions: '.exe' })).toThrow();
  });
});
