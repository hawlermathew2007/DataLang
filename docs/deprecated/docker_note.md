## Change the network mode
By default, each service joins the project's bridge network. It is the most secure networking mode. If you don't specify network_mode, this is the type of network you are creating.

You can override the networking mode on a per-service basis. The network_mode option accepts the following values:

- host: The container shares the host's network stack. No port mapping is needed or supported, and service name DNS resolution does not work. Use for system-level tools like network monitors that require direct access to host interfaces. A container using network_mode: host can access all host ports and observe all network traffic on the host. Use it only when genuinely required.
- none: Turns off all container networking.
- service:{name}: Gives the container access to the specified container by referring to its service name.
- container:{name}: Gives the container access to the specified container by referring to its container ID.
