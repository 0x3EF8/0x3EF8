import java.util.*;
import java.io.*;
import java.net.*;

class Active {

    public static void main(String[] sg) {
        Runnable re = () -> {
            try {
            File folder = new File("gen");
            if (!folder.exists()) {
                folder.mkdir();
            }
            File fe = new File("gen/README.yml");
            FileWriter fw = new FileWriter(fe);
            BufferedWriter bufferedWriter = new BufferedWriter(fw);
            bufferedWriter.write(new Date().toString());
            bufferedWriter.close();
            fw.close();
            System.out.println("Successfully generate file");
            } catch (Exception en) {
                System.out.println("Failed to generate file: " + en.getMessage());
            }
        };
        new Thread(re).start();
    }
}