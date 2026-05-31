/**
 * Estado vacío server-rendered para las páginas /me cuando el usuario logueado no
 * tiene un perfil de doctor (el backend responde 403 NOT_A_DOCTOR). Es un caso de
 * negocio (p. ej. un admin sin perfil de doctor), NO un 404 ni un crash.
 *
 * Server Component a propósito: sin `makeStyles`/hooks → se renderiza en el RSC sin
 * "use client". Usa estilos inline para no depender de Fluent en server.
 */

interface Props {
  title: string;
}

export function NotADoctorNotice({ title }: Props) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "12px",
        padding: "64px 24px",
        textAlign: "center",
      }}
    >
      <h1
        style={{
          margin: 0,
          fontSize: "20px",
          fontWeight: 600,
        }}
      >
        {title}
      </h1>
      <p
        style={{
          margin: 0,
          maxWidth: "420px",
          fontSize: "14px",
          color: "#616161",
        }}
      >
        Tu cuenta no tiene un perfil de doctor asociado. Si crees que es un error, contacta al
        administrador.
      </p>
    </div>
  );
}
